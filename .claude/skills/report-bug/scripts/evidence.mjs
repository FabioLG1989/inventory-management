#!/usr/bin/env node
/**
 * Moves report-bug evidence files without ever handing a report-controlled
 * path to a shell. Every path in a failure report (attachment paths, Detox
 * artifact folders named after test titles) is untrusted: the agent writes
 * them into a JSON manifest with its file-writing tool, and this script reads
 * the manifest, confines every path to the project root and calls `curl` /
 * `zip` through execFile with an argument array.
 *
 * The project root is never taken from the manifest: it is the git top level
 * of the working directory (or the working directory outside git), so a
 * manifest written from untrusted report content cannot widen it.
 *
 * Inside the root, hidden files and folders (`.env*`, `.git/`, `.npmrc`, …)
 * are rejected because that is where credentials live; only the framework's
 * temp folder (`.claude-temp` / `.codex-temp`) is exempt, and it is the only
 * place `snapshot` and `zip` may write.
 *
 * Usage (from the project root): node evidence.mjs <check|snapshot|zip|put|jira-attach|redact|sanitize> <manifest.json>
 *
 *   check        {files[]}                    → accepted[{path, resolved, size, contentType}], rejected[{path, reason}]
 *   snapshot     {dest, files[], dirs[]}      → copies[{path, copy}], rejected[]
 *   zip          {dir, out}                   → {out, size}
 *   put          {file, url, headers{}}       → {status, ok, error?}
 *   jira-attach  {site, issue, files[]}       → results[{path, status, ok, id, error?}], rejected[]
 *   redact       {text}                       → {text, redactions[{kind, count}]}
 *   sanitize     {files[]}                    → files[{path, upload, size, contentType, redactions[]}], rejected[]
 *
 * A transport failure (DNS, refused connection, timeout) is reported per file
 * as `ok: false` with `error`, never by aborting the batch, so earlier uploads
 * stay accounted for.
 *
 * `jira-attach` reads JIRA_EMAIL / JIRA_API_TOKEN from the environment, or
 * from `<root>/.env.local` when unset, and hands them to curl on stdin
 * (`--config -`) so they never appear in the process list or in the output.
 * Exit code 3 means credentials are missing; the adapter then falls back to
 * listing paths in a comment.
 *
 * Pure Node builtins plus the `curl` and `zip` binaries.
 */
import { execFileSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { devNull, homedir, tmpdir } from "node:os";
import { basename, dirname, extname, isAbsolute, join, parse, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

/** Content types for the evidence extensions test runners produce. */
export const CONTENT_TYPES = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webm": "video/webm",
  ".mp4": "video/mp4",
  ".zip": "application/zip",
  ".json": "application/json",
  ".md": "text/markdown",
  ".html": "text/html",
  ".txt": "text/plain",
  ".log": "text/plain",
};

/** The framework temp folders: the only hidden folder evidence may live in, and the only place new files are written. */
export const TEMP_DIRS = [".claude-temp", ".codex-temp"];

/** Hosts `put` may upload to: the signed-URL storage behind Linear's attachment uploads. */
export const PUT_HOSTS = ["storage.googleapis.com"];

/**
 * The only buckets `put` may upload to on PUT_HOSTS, by exact name: the ones
 * Linear's signed upload URLs point at. Bucket names on that host are one
 * global first-come namespace, so a pattern would admit a bucket anyone can
 * register.
 */
export const PUT_BUCKETS = ["linear-uploads-us-central1"];

/**
 * Names of text/JSON files that hold credentials (`credentials.json`,
 * `google-services.json`, …). Screenshots, videos and `.log` files are never
 * matched: runners and failure hooks name them after test titles, which often
 * mention credentials, and every log is redacted before upload.
 */
const CREDENTIAL_FILE = /(credential|secret|service[-_]?account|google-services|firebase-adminsdk|keystore)/i;

/** True for a text or JSON file whose name marks it as a credentials file. */
function isCredentialFile(path) {
  const type = CONTENT_TYPES[extname(path).toLowerCase()] ?? "";
  return (
    extname(path).toLowerCase() !== ".log" &&
    (type.startsWith("text/") || type === "application/json") &&
    CREDENTIAL_FILE.test(basename(path))
  );
}

/** Bounds every curl call so a stalled connection fails instead of hanging the run. */
const CURL_LIMITS = ["--connect-timeout", "30", "--max-time", "600"];

/**
 * A key name that holds a secret, as a regex source: a secret keyword with an
 * optional `key`/`key_base`/`id` suffix (`SECRET_KEY`, `session_id`).
 */
const SECRET_KEY = String.raw`(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key|cookie|session|sid|auth)(?:[_-]?(?:key(?:[_-]?base)?|id))?`;

/**
 * Assignment labels whose key only hints at a secret (`session`, `sid`,
 * `auth`): their value is masked only when it looks like one, so log text
 * such as `session: started` stays readable.
 */
const WEAK_SECRET_LABEL = /(?:session|sid|auth)(?:[_-]?id)?(?:\\?["'])?\s*[:=]\s*$/i;

/**
 * Secret shapes masked by `redact`, as [kind, pattern, replacement]. The
 * replacement keeps the label (scheme, key name) and drops only the value.
 */
export const SECRET_PATTERNS = [
  ["private-key", /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g, "[REDACTED PRIVATE KEY]"],
  [
    "authorization",
    /\b(Bearer|Basic|Token)\s+([A-Za-z0-9._~+/=-]{8,})/g,
    (match, scheme, value) => (/^[A-Z]?[a-z]+$/.test(value) ? match : `${scheme} [REDACTED]`),
  ],
  ["github-token", /\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})/g, "[REDACTED]"],
  ["slack-token", /\bxox[abposr]-[A-Za-z0-9-]{10,}/g, "[REDACTED]"],
  ["api-key", /\bsk-ant-[A-Za-z0-9_-]{20,}/g, "[REDACTED]"],
  ["api-key", /\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}/g, "[REDACTED]"],
  ["api-key", /\bAIza[0-9A-Za-z_-]{35}/g, "[REDACTED]"],
  ["aws-access-key", /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g, "[REDACTED]"],
  ["jwt", /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g, "[REDACTED]"],
  ["url-credentials", /(\b[a-z][a-z0-9+.-]*:\/\/)[^\s:@/]+:[^\s@/]+@/gi, "$1[REDACTED]@"],
  [
    "header",
    new RegExp(
      String.raw`("name"\s*:\s*"[A-Za-z0-9_.-]*?(?:authorization|${SECRET_KEY})"\s*,\s*"value"\s*:\s*")(?:\\.|[^"\\])*(")`,
      "gi",
    ),
    "$1[REDACTED]$2",
  ],
  [
    "header",
    /("(?:proxy-)?authorization"\s*:\s*")(?!(?:(?:Bearer|Basic|Token)\s+)?\[REDACTED)(?:\\.|[^"\\])+(")/gi,
    "$1[REDACTED]$2",
  ],
  [
    "storage-value",
    /("(?:cookies|localStorage)"\s*:\s*\[)((?:[^[\]"]|"(?:\\.|[^"\\])*")*)\]/g,
    (_, open, entries) => `${open}${entries.replace(/("value"\s*:\s*")(?:\\.|[^"\\])*(")/g, "$1[REDACTED]$2")}]`,
  ],
  [
    "header",
    /^(\s*(?:cookie|set-cookie|authorization|proxy-authorization|x-api-key|x-auth-token)\s*:\s*)(?!(?:(?:Bearer|Basic|Token)\s+)?\[REDACTED)\S.*$/gim,
    "$1[REDACTED]",
  ],
  [
    "secret-assignment",
    new RegExp(
      String.raw`(?<![A-Za-z0-9])([A-Za-z0-9]*?${SECRET_KEY}(?:\\?["'])?\s*[:=]\s*)(?:\\"(?!\[REDACTED|\\")((?:\\\\(?:\\.|[^\\\n])|\\[^"\\\n]|[^\\"\n])+)((?:\\")?)|"(?!\[REDACTED|")((?:\\.|[^"\\\n])+)("?)|'(?!\[REDACTED|')((?:\\.|[^'\\\n])+)('?)|(?!\[REDACTED|(?:null|true|false)\b|["'\\])((?:\\(?!["'])|[^\s"'\\&,;}\]]){4,}))`,
      "gi",
    ),
    (match, label, escaped, escapedClose, double, doubleClose, single, singleClose, bare) => {
      if (WEAK_SECRET_LABEL.test(label) && !looksSecret(escaped ?? double ?? single ?? bare)) {
        return match;
      }
      if (escaped !== undefined) {
        return `${label}\\"[REDACTED]${escapedClose}`;
      }
      if (double !== undefined) {
        return `${label}"[REDACTED]${doubleClose}`;
      }
      if (single !== undefined) {
        return `${label}'[REDACTED]${singleClose}`;
      }
      if (!/"\s*:\s*$/.test(label)) {
        return `${label}[REDACTED]`;
      }
      const mark = /\\"\s*:\s*$/.test(label) ? '\\"' : '"';
      return `${label}${mark}[REDACTED]${mark}`;
    },
  ],
];

/**
 * Variable names — in the environment or the project's `.env*` files — whose
 * values `redact` masks wherever they appear. Other `.env` values
 * (`BASE_URL`, `NODE_ENV`, `PORT`) are configuration, and stay readable.
 */
const SECRET_ENV_NAME =
  /(TOKEN|SECRET|PASS|PWD|KEY|CREDENTIAL|COOKIE|SESSION|AUTH|SALT|SIGNATURE|PRIVATE|DSN|CONNECTION_?STRING|(^|_)(SK|PK)(_|$))/i;

/**
 * Names that say outright that the value is a secret. Their values are
 * masked even when they read like plain words (`API_KEY`, `DB_PASSWORD`);
 * names that only match SECRET_ENV_NAME through `AUTH`, `SESSION`, `COOKIE`
 * or a `KEY` that doesn't end the name (`CACHE_KEY_PREFIX`, `AUTH_PROVIDER`)
 * need a value that looks like one.
 */
const STRONG_SECRET_NAME = /(TOKEN|SECRET|PASS|PWD|CREDENTIAL|PRIVATE|SIGNATURE|SALT|DSN|CONNECTION_?STRING|KEY$|(^|_)(SK|PK)(_|$))/i;

/** Names that hold an address, never a secret, even when they contain `KEY` or `AUTH` (`KEYCLOAK_HOST`). */
const ADDRESS_ENV_NAME = /_(HOST|HOSTNAME|PORT)$/i;

/**
 * Shell and runtime variables whose names match SECRET_ENV_NAME but whose
 * values are working state, never secrets: the current folder (`PWD` is the
 * project root, so masking it would erase every stack-trace path), the
 * terminal session, the SSH agent socket, and git credential helper paths.
 */
const RUNTIME_ENV_NAME = /^(?:PWD|OLDPWD|SSH_AUTH_SOCK|TERM_SESSION_ID|ITERM_SESSION_ID|SECURITYSESSIONID)$|ASKPASS/i;

/**
 * True when `value` has the shape of a secret: 8+ characters mixing at least
 * two of lowercase, uppercase, digits and symbols, or, when `wordsCount` is
 * set, any 8+ character value. Integers and booleans are configuration, and
 * so are plain words (`database`, `checkout-flow`) unless `wordsCount`. A
 * URL is a secret only when it carries user-info or a path/query segment that
 * itself looks like one (`NEXTAUTH_URL=http://localhost:3000/api/auth` stays
 * readable; a webhook URL with a random path does not).
 */
function looksSecret(value, wordsCount = false) {
  const text = value.trim();
  if (text.length < 8 || /^\d+$/.test(text) || /^(?:true|false|null|none|yes|no|on|off)$/i.test(text)) {
    return false;
  }
  const url = text.match(/^[a-z][a-z0-9+.-]*:\/\/([^/?#\s]*)(.*)$/i);
  if (url) {
    return url[1].includes("@") || url[2].split(/[/?&=#;]/).some((segment) => looksSecret(segment));
  }
  if (/^[A-Za-z]+(?:[-_. ][A-Za-z]+)*$/.test(text)) {
    return wordsCount;
  }
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((pattern) => pattern.test(text));
  return wordsCount || classes.length >= 2;
}

/**
 * True when `name`'s `value` is a secret worth masking wherever it appears.
 * A value naming an existing absolute path (`GOOGLE_APPLICATION_CREDENTIALS`)
 * is where a secret lives, not the secret, and stays readable.
 */
function isSecretVariable(name, value) {
  return (
    typeof value === "string" &&
    SECRET_ENV_NAME.test(name) &&
    !ADDRESS_ENV_NAME.test(name) &&
    !RUNTIME_ENV_NAME.test(name) &&
    !(isAbsolute(value) && existsSync(value)) &&
    looksSecret(value, STRONG_SECRET_NAME.test(name))
  );
}

/** A zip embedded in text as a data URL — how Playwright's HTML reporter stores its data in `index.html`. */
const EMBEDDED_ZIP = /data:application\/zip;base64,([A-Za-z0-9+/=]+)/g;

/** How many archive levels `sanitize` descends into (zipped report → trace.zip → embedded data); deeper is rejected. */
const MAX_ARCHIVE_DEPTH = 3;

const JIRA_SITE = /^[a-z0-9][a-z0-9-]*\.atlassian\.net$/;
const JIRA_ISSUE = /^[A-Z][A-Z0-9_]*-[0-9]+$/;

/**
 * The project root: the git top level of `cwd`, or `cwd` itself outside a
 * git work tree. Refuses the filesystem root and the home directory, which
 * would make every containment check meaningless.
 */
export function projectRoot(cwd = process.cwd()) {
  let root = cwd;
  try {
    root = execFileSync("git", ["rev-parse", "--show-toplevel"], {
      cwd,
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    root = cwd;
  }
  const real = realpathSync(root);
  if (real === parse(real).root || real === realpathSync(homedir())) {
    throw new Error(`refusing ${real} as the project root; run from the project folder`);
  }
  return real;
}

/** Stderr of a failed child process, or the error message when there is none. */
function failureText(error) {
  return error.stderr?.toString().trim() || error.message;
}

/** Path segments of `real` below `rootReal`. */
function segmentsBelow(rootReal, real) {
  return relative(rootReal, real).split(sep).filter(Boolean);
}

/** True when a segment below the root is hidden, ignoring a leading framework temp folder. */
function isHidden(rootReal, real) {
  const segments = segmentsBelow(rootReal, real);
  const rest = TEMP_DIRS.includes(segments[0]) ? segments.slice(1) : segments;
  return rest.some((segment) => segment.startsWith("."));
}

/**
 * Resolves `candidate` against `root` and returns the real path when it stays
 * inside the root, is not hidden, and has the expected kind — a file with a
 * known evidence extension, or a folder other than the root itself;
 * otherwise a rejection reason.
 */
export function confine(root, candidate, kind = "file") {
  if (typeof candidate !== "string" || candidate.length === 0) {
    return { reason: "empty path" };
  }
  const rootReal = realpathSync(root);
  const joined = isAbsolute(candidate) ? candidate : resolve(rootReal, candidate);
  if (!existsSync(joined)) {
    return { reason: "not found" };
  }
  const real = realpathSync(joined);
  if (!isInside(rootReal, real)) {
    return { reason: "outside the project root" };
  }
  if (isHidden(rootReal, real)) {
    return { reason: "hidden file or folder" };
  }
  const stat = statSync(real);
  if (kind === "file" && !stat.isFile()) {
    return { reason: "not a regular file" };
  }
  if (kind === "file" && !(extname(real).toLowerCase() in CONTENT_TYPES)) {
    return { reason: "unsupported evidence type" };
  }
  if (kind === "file" && isCredentialFile(real)) {
    return { reason: "credential-like file name" };
  }
  if (kind === "dir" && !stat.isDirectory()) {
    return { reason: "not a directory" };
  }
  if (kind === "dir" && real === rootReal) {
    return { reason: "the project root itself" };
  }
  return { resolved: real, size: stat.size };
}

/** True when `path` is `rootReal` or lies beneath it. */
function isInside(rootReal, path) {
  return path === rootReal || path.startsWith(rootReal + sep);
}

/**
 * Resolves a path that is about to be created, which must sit inside a
 * framework temp folder. Containment is checked before any directory is
 * created, through the real path of the nearest existing ancestor so a
 * symlink inside the root cannot redirect the new folders outside it, and
 * again on the created parent.
 */
function confineNew(root, candidate) {
  const rootReal = realpathSync(root);
  const target = isAbsolute(candidate) ? candidate : resolve(rootReal, candidate);
  let ancestor = dirname(target);
  while (!existsSync(ancestor)) {
    ancestor = dirname(ancestor);
  }
  const resolvedTarget = join(realpathSync(ancestor), relative(ancestor, target));
  if (!isInside(rootReal, resolvedTarget)) {
    throw new Error(`${candidate}: outside the project root`);
  }
  if (!TEMP_DIRS.includes(segmentsBelow(rootReal, resolvedTarget)[0])) {
    throw new Error(`${candidate}: must be inside ${TEMP_DIRS.join(" or ")}`);
  }
  mkdirSync(dirname(target), { recursive: true });
  const parent = realpathSync(dirname(target));
  if (!isInside(rootReal, parent)) {
    throw new Error(`${candidate}: outside the project root`);
  }
  return join(parent, basename(target));
}

/** Splits `files` into confined, typed entries and rejections. */
export function check(root, files = []) {
  const accepted = [];
  const rejected = [];
  for (const path of files) {
    const result = confine(root, path);
    if (result.reason) {
      rejected.push({ path, reason: result.reason });
      continue;
    }
    accepted.push({
      path,
      resolved: result.resolved,
      size: result.size,
      contentType: CONTENT_TYPES[extname(result.resolved).toLowerCase()],
    });
  }
  return { accepted, rejected };
}

/**
 * Copies evidence files and folders under `dest`, keeping their path relative
 * to the root, so a confirmation re-run cannot overwrite or delete them.
 * Hidden entries inside a copied folder are skipped. A copy that fails is
 * reported in `rejected` and the rest still run.
 */
export function snapshot(root, dest, files = [], dirs = []) {
  const rootReal = realpathSync(root);
  const destReal = confineNew(root, join(dest, ".keep"));
  const destDir = dirname(destReal);
  const copies = [];
  const rejected = [];
  for (const [kind, list] of [["file", files], ["dir", dirs]]) {
    for (const path of list) {
      const result = confine(root, path, kind);
      if (result.reason) {
        rejected.push({ path, reason: result.reason });
        continue;
      }
      const segments = relative(rootReal, result.resolved).split(sep);
      const origin = TEMP_DIRS.includes(segments[0]) ? ["temp", ...segments.slice(1)] : ["project", ...segments];
      const copy = join(destDir, ...origin);
      try {
        mkdirSync(dirname(copy), { recursive: true });
        cpSync(result.resolved, copy, {
          recursive: kind === "dir",
          preserveTimestamps: true,
          filter: (source) => source === result.resolved || !basename(source).startsWith("."),
        });
        copies.push({ path, copy });
      } catch (error) {
        rejected.push({ path, reason: error.message });
      }
    }
  }
  return { copies, rejected };
}

/**
 * Raised when `zip` or `unzip` is not on PATH (stock Windows, slim CI
 * images): `tool` names the missing one so callers can fall back instead of
 * reporting a raw spawn error.
 */
export class MissingToolError extends Error {
  constructor(tool) {
    super(`${tool} is not installed, so archives can't be built or sanitized on this machine`);
    this.tool = tool;
  }
}

/** Runs an archive tool, turning a missing executable into a MissingToolError. */
function runArchiver(tool, args, options) {
  try {
    execFileSync(tool, args, options);
  } catch (error) {
    if (error.code === "ENOENT") {
      throw new MissingToolError(tool);
    }
    throw error;
  }
}

/**
 * Zips a confined directory into a `.zip` inside the temp folder. Symlinks
 * are stored as links (`-y`), so a link inside the folder never pulls in a
 * file from outside the project root, and hidden entries are left out.
 */
export function zip(root, dir, out) {
  const source = confine(root, dir, "dir");
  if (source.reason) {
    throw new Error(`${dir}: ${source.reason}`);
  }
  if (typeof out !== "string" || !out.endsWith(".zip")) {
    throw new Error(`${out}: the output must be a .zip file`);
  }
  const target = confineNew(root, out);
  rmSync(target, { force: true });
  runArchiver("zip", ["-r", "-q", "-y", target, `.${sep}${basename(source.resolved)}`, "-x", "*/.*"], {
    cwd: dirname(source.resolved),
    stdio: ["ignore", "ignore", "pipe"],
  });
  return { out: target, size: statSync(target).size };
}

/** Escapes a value for a double-quoted curl `-F` / config string. */
export function curlQuote(value) {
  return `"${String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

/**
 * PUTs one confined file to a signed upload URL, sending every header
 * verbatim and the file's content type when the headers carry none. A
 * transport failure comes back as `ok: false` with `error`.
 */
export function put(root, file, url, headers = {}) {
  const source = confine(root, file);
  if (source.reason) {
    throw new Error(`${file}: ${source.reason}`);
  }
  if (headers === null || typeof headers !== "object" || Array.isArray(headers)) {
    throw new Error("headers must be an object of header name to string value");
  }
  const entries = Object.entries(headers);
  if (entries.some(([, value]) => typeof value !== "string")) {
    throw new Error("every header value must be a string");
  }
  if (!entries.some(([name]) => name.toLowerCase() === "content-type")) {
    entries.push(["Content-Type", CONTENT_TYPES[extname(source.resolved).toLowerCase()]]);
  }
  const args = [...CURL_LIMITS, "-sS", "-o", devNull, "-w", "%{http_code}", "-X", "PUT", "--data-binary", `@${source.resolved}`];
  for (const [name, value] of entries) {
    args.push("-H", `${name}: ${value}`);
  }
  args.push(url);
  try {
    const status = Number(execFileSync("curl", args, { encoding: "utf-8", stdio: ["ignore", "pipe", "pipe"] }).trim());
    return { status, ok: status >= 200 && status < 300 };
  } catch (error) {
    return { status: null, ok: false, error: failureText(error) };
  }
}

/**
 * Reads KEY=VALUE pairs from a dotenv file, ignoring comment lines and
 * `export`. Quoted values are taken verbatim; unquoted values lose a trailing
 * ` # comment` and surrounding whitespace.
 */
export function readDotenv(path) {
  if (!existsSync(path)) {
    return {};
  }
  const values = {};
  for (const line of readFileSync(path, "utf-8").split(/\r?\n/)) {
    const match = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!match) {
      continue;
    }
    const quoted = match[2].match(/^(['"])(.*?)\1/);
    values[match[1]] = quoted ? quoted[2] : match[2].replace(/\s+#.*$/, "").trim();
  }
  return values;
}

/**
 * The project's `.env*` files, tracked or not — a suite in a subfolder keeps
 * its own (`e2e/.env`) — or, outside git, the ones at the root.
 */
function dotenvFiles(root) {
  try {
    const listed = execFileSync(
      "git",
      ["ls-files", "-z", "--cached", "--others", "--exclude=node_modules/", "--", ":(glob)**/.env", ":(glob)**/.env.*"],
      { cwd: root, encoding: "utf-8", stdio: ["ignore", "pipe", "ignore"] },
    );
    return [...new Set(listed.split("\0").filter(Boolean))].map((file) => join(root, file));
  } catch {
    return readdirSync(root)
      .filter((name) => /^\.env(\..+)?$/.test(name))
      .map((name) => join(root, name));
  }
}

/**
 * Values (longest first) of every secret-named variable in the project's
 * `.env*` files and in `env` whose value looks like a secret (see
 * `looksSecret`) — built once per run.
 */
export function secretValues(root, env = process.env) {
  const known = new Set();
  const rootReal = realpathSync(root);
  for (const file of dotenvFiles(root)) {
    let real;
    try {
      real = realpathSync(file);
    } catch {
      continue;
    }
    if (!isInside(rootReal, real) || !statSync(real).isFile()) {
      continue;
    }
    for (const [key, value] of Object.entries(readDotenv(real))) {
      if (isSecretVariable(key, value)) {
        known.add(value);
      }
    }
  }
  for (const [name, value] of Object.entries(env)) {
    if (isSecretVariable(name, value)) {
      known.add(value);
    }
  }
  return [...known].sort((a, b) => b.length - a.length);
}

/** Masks `known` values and SECRET_PATTERNS in `text`, adding each kind's count to `totals`. */
function redactText(text, known, totals) {
  let result = String(text);
  const note = (kind, amount) => amount > 0 && totals.set(kind, (totals.get(kind) ?? 0) + amount);
  for (const value of known) {
    const parts = result.split(value);
    note("known-secret", parts.length - 1);
    result = parts.join("[REDACTED]");
  }
  const masks = () => result.split("[REDACTED").length;
  for (const [kind, pattern, replacement] of SECRET_PATTERNS) {
    const before = masks();
    result = result.replace(pattern, replacement);
    note(kind, masks() - before);
  }
  return result;
}

/** `{kind, count}` entries of a totals map. */
function summary(totals) {
  return [...totals].map(([kind, count]) => ({ kind, count }));
}

/**
 * Masks secrets in `text` before it is published: the shapes in
 * SECRET_PATTERNS, plus every value of a secret-named variable, from the
 * project's `.env*` files or the environment.
 */
export function redact(root, text, env = process.env) {
  const totals = new Map();
  const result = redactText(text, secretValues(root, env), totals);
  return { text: result, redactions: summary(totals) };
}

/**
 * Static code a Playwright report or trace bundles from playwright-core: no
 * run data, and code the text patterns would turn into syntax errors.
 */
const BUNDLED_CODE = new Set([".js", ".mjs", ".css"]);

/**
 * Decodes `buffer` as text with the encoding that writes it back byte for
 * byte, or returns null for binary content: UTF-16 by its byte-order mark,
 * then UTF-8, then Latin-1 — which maps every byte, so text that isn't valid
 * UTF-8 is still redacted instead of passed through.
 */
function asText(buffer) {
  if (buffer[0] === 0xff && buffer[1] === 0xfe) {
    return { text: buffer.toString("utf16le"), encoding: "utf16le" };
  }
  if (buffer[0] === 0xfe && buffer[1] === 0xff && buffer.length % 2 === 0) {
    return { text: Buffer.from(buffer).swap16().toString("utf16le"), encoding: "utf16be" };
  }
  if (buffer.includes(0)) {
    return null;
  }
  try {
    return { text: new TextDecoder("utf-8", { fatal: true }).decode(buffer), encoding: "utf-8" };
  } catch {
    return { text: buffer.toString("latin1"), encoding: "latin1" };
  }
}

/** `text` as bytes in `encoding`, the inverse of `asText`. */
function encodeText(text, encoding) {
  return encoding === "utf16be" ? Buffer.from(text, "utf16le").swap16() : Buffer.from(text, encoding);
}

/**
 * Redacts a text document. A document that embeds zips as base64 data URLs
 * (a Playwright HTML report) only has those archives rebuilt with their
 * entries redacted: the rest of it is the report's bundled app, not run data.
 */
function redactDocument(context, text, depth) {
  let embedsArchive = false;
  const withArchives = text.replace(EMBEDDED_ZIP, (_, base64) => {
    embedsArchive = true;
    if (depth <= 0) {
      throw new Error("archive nested too deep to sanitize");
    }
    const scratch = mkdtempSync(join(tmpdir(), "report-bug-embedded-"));
    try {
      const archive = join(scratch, "embedded.zip");
      writeFileSync(archive, Buffer.from(base64, "base64"));
      redactArchive(context, archive, archive, depth - 1);
      return `data:application/zip;base64,${readFileSync(archive).toString("base64")}`;
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  });
  return embedsArchive ? withArchives : redactText(withArchives, context.known, context.totals);
}

/**
 * Redacts every text file under `dir` in place and rebuilds nested `.zip`
 * archives the same way; media files and bundled `.js`/`.mjs`/`.css` code are
 * left untouched. An archive deeper than `depth` allows is an error, never
 * passed through unredacted.
 */
function redactTree(context, dir, depth) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      redactTree(context, path, depth);
      continue;
    }
    if (!entry.isFile()) {
      rmSync(path, { force: true });
      continue;
    }
    if (extname(entry.name).toLowerCase() === ".zip") {
      if (depth <= 0) {
        throw new Error("archive nested too deep to sanitize");
      }
      redactArchive(context, path, path, depth - 1);
      continue;
    }
    if (BUNDLED_CODE.has(extname(entry.name).toLowerCase())) {
      continue;
    }
    const decoded = asText(readFileSync(path));
    if (decoded === null) {
      continue;
    }
    const result = redactDocument(context, decoded.text, depth);
    if (result !== decoded.text) {
      writeFileSync(path, encodeText(result, decoded.encoding));
    }
  }
}

/**
 * Extracts `source` into a scratch folder, redacts its entries, and writes
 * the re-zipped result to `target`. Symlinks inside the archive are dropped
 * rather than followed.
 */
function redactArchive(context, source, target, depth) {
  const scratch = mkdtempSync(join(tmpdir(), "report-bug-sanitize-"));
  try {
    runArchiver("unzip", ["-qq", "-o", source, "-d", scratch], { stdio: ["ignore", "ignore", "pipe"] });
    redactTree(context, scratch, depth);
    rmSync(target, { force: true });
    runArchiver("zip", ["-r", "-q", target, "."], { cwd: scratch, stdio: ["ignore", "ignore", "pipe"] });
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

/**
 * Prepares files for upload: a text file (log, stack dump, JSON report,
 * markdown, HTML — including the zip an HTML report embeds) gets a redacted
 * copy, and an archive (Playwright `trace.zip`, a zipped report) is rebuilt
 * with every entry redacted — traces carry request headers and cookies.
 * Media files upload as they are. A file that can't be fully sanitized is
 * rejected, never uploaded as is.
 *
 * Copies go under `<temp>/report-bug/sanitized/`, split into `project/`
 * (files from the project tree) and `temp/` (files already in a temp
 * folder) so two inputs never share a copy. `<temp>` is the temp folder the
 * file came from, else `preferredTemp` (the one holding the manifest), else
 * the one the project has. Upload `upload`, never `path`.
 */
export function sanitize(root, files = [], preferredTemp = null, env = process.env) {
  const rootReal = realpathSync(root);
  const { accepted, rejected } = check(root, files);
  const known = secretValues(root, env);
  const out = [];
  for (const entry of accepted) {
    const type = entry.contentType;
    const isText = type.startsWith("text/") || type === "application/json";
    const isArchive = type === "application/zip";
    if (!isText && !isArchive) {
      out.push({ path: entry.path, upload: entry.resolved, size: entry.size, contentType: type, redactions: [] });
      continue;
    }
    const segments = relative(rootReal, entry.resolved).split(sep);
    const inTemp = TEMP_DIRS.includes(segments[0]);
    const tempDir = inTemp
      ? segments[0]
      : (preferredTemp ?? TEMP_DIRS.find((dir) => existsSync(join(rootReal, dir))) ?? TEMP_DIRS[0]);
    const origin = inTemp ? ["temp", ...segments.slice(1)] : ["project", ...segments];
    const copy = confineNew(root, join(tempDir, "report-bug", "sanitized", ...origin));
    const context = { known, totals: new Map() };
    try {
      if (isText) {
        writeFileSync(copy, redactDocument(context, readFileSync(entry.resolved, "utf-8"), MAX_ARCHIVE_DEPTH));
      } else {
        redactArchive(context, entry.resolved, copy, MAX_ARCHIVE_DEPTH - 1);
      }
      out.push({ path: entry.path, upload: copy, size: statSync(copy).size, contentType: type, redactions: summary(context.totals) });
    } catch (error) {
      rmSync(copy, { force: true });
      rejected.push(
        error instanceof MissingToolError
          ? { path: entry.path, reason: `could not sanitize: ${error.message}`, missingTool: error.tool }
          : { path: entry.path, reason: `could not sanitize: ${failureText(error)}` },
      );
    }
  }
  return { files: out, rejected };
}

/** Resolves Jira credentials from the environment, then `<root>/.env.local`. */
export function jiraCredentials(root, env = process.env) {
  const local = readDotenv(join(root, ".env.local"));
  const email = env.JIRA_EMAIL || local.JIRA_EMAIL;
  const token = env.JIRA_API_TOKEN || local.JIRA_API_TOKEN;
  return email && token ? { email, token } : null;
}

/**
 * Uploads confined files to `<baseUrl>/rest/api/3/issue/<issue>/attachments`.
 * Credentials travel on curl's stdin, never in argv. A transport failure on
 * one file is recorded and the loop moves on to the next.
 */
export function attachToJira(root, baseUrl, issue, files, credentials) {
  const { accepted, rejected } = check(root, files);
  const scratch = mkdtempSync(join(tmpdir(), "report-bug-"));
  const results = [];
  try {
    for (const entry of accepted) {
      const response = join(scratch, "response.json");
      rmSync(response, { force: true });
      let status;
      try {
        status = Number(
          execFileSync(
            "curl",
            [
              "--config", "-",
              ...CURL_LIMITS,
              "-sS", "-o", response, "-w", "%{http_code}",
              "-X", "POST",
              "-H", "X-Atlassian-Token: no-check",
              "-F", `file=@${curlQuote(entry.resolved)}`,
              `${baseUrl}/rest/api/3/issue/${issue}/attachments`,
            ],
            {
              encoding: "utf-8",
              input: `user = ${curlQuote(`${credentials.email}:${credentials.token}`)}\n`,
              stdio: ["pipe", "pipe", "pipe"],
            },
          ).trim(),
        );
      } catch (error) {
        results.push({ path: entry.path, status: null, ok: false, id: null, error: failureText(error) });
        continue;
      }
      let id = null;
      try {
        id = JSON.parse(readFileSync(response, "utf-8"))?.[0]?.id ?? null;
      } catch {
        id = null;
      }
      results.push({ path: entry.path, status, ok: status >= 200 && status < 300, id });
    }
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
  return { results, rejected };
}

/**
 * True for an https URL on one of PUT_HOSTS, in one of PUT_BUCKETS. A
 * backslash, `@`, whitespace or userinfo is refused outright: WHATWG URL and
 * curl parse those differently, so the host checked here could differ from the
 * host curl connects to. Signed upload URLs never contain them.
 */
export function isAllowedUploadUrl(url) {
  try {
    const parsed = new URL(url);
    const bucket = parsed.pathname.split("/")[1] ?? "";
    return (
      !/[\\@\s]/.test(url) &&
      parsed.username === "" &&
      parsed.password === "" &&
      parsed.protocol === "https:" &&
      PUT_HOSTS.includes(parsed.hostname) &&
      PUT_BUCKETS.includes(bucket)
    );
  } catch {
    return false;
  }
}

function main(argv) {
  const [command, manifestPath] = argv;
  if (!command || !manifestPath) {
    process.stderr.write("Usage: node evidence.mjs <check|snapshot|zip|put|jira-attach|redact|sanitize> <manifest.json>\n");
    return 2;
  }
  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
  const root = projectRoot();
  let output;
  switch (command) {
    case "check":
      output = check(root, manifest.files);
      break;
    case "snapshot":
      output = snapshot(root, manifest.dest, manifest.files, manifest.dirs);
      break;
    case "zip":
      output = zip(root, manifest.dir, manifest.out);
      break;
    case "put":
      if (!isAllowedUploadUrl(manifest.url)) {
        process.stderr.write(`url must be the https upload URL the adapter returned (${PUT_HOSTS.join(", ")})\n`);
        return 2;
      }
      output = put(root, manifest.file, new URL(manifest.url).href, manifest.headers);
      break;
    case "jira-attach": {
      if (!JIRA_SITE.test(manifest.site ?? "") || !JIRA_ISSUE.test(manifest.issue ?? "")) {
        process.stderr.write("site must be <name>.atlassian.net and issue a Jira key like PROJ-123\n");
        return 2;
      }
      const credentials = jiraCredentials(root);
      if (!credentials) {
        process.stdout.write(`${JSON.stringify({ error: "missing-credentials" })}\n`);
        return 3;
      }
      output = attachToJira(root, `https://${manifest.site}`, manifest.issue, manifest.files, credentials);
      break;
    }
    case "redact":
      output = redact(root, manifest.text ?? "");
      break;
    case "sanitize": {
      const manifestTemp = relative(root, realpathSync(manifestPath)).split(sep)[0];
      output = sanitize(root, manifest.files, TEMP_DIRS.includes(manifestTemp) ? manifestTemp : null);
      break;
    }
    default:
      process.stderr.write(`Unknown command: ${command}\n`);
      return 2;
  }
  process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
  return 0;
}

if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    process.exitCode = main(process.argv.slice(2));
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}
