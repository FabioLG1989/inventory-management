---
name: design-doc-mermaid
description: Create architectural diagrams, flowcharts, sequence diagrams, and entity-relationship diagrams using Mermaid syntax for technical documentation
---

# Design Doc Mermaid Skill

Generate comprehensive technical diagrams using Mermaid syntax for design documents, pull requests, and architecture documentation.

## When to Use

- Documenting system architecture for PRs
- Creating sequence diagrams for API workflows
- Visualizing database schemas (ERD)
- Showing state machines or flowcharts
- Explaining data flows between services

## Supported Diagram Types

### 1. Flowchart

**Use for**: Decision trees, process flows, algorithm logic

```mermaid
flowchart TD
    A[Start] --> B{Is authenticated?}
    B -->|Yes| C[Load Dashboard]
    B -->|No| D[Redirect to Login]
    C --> E[Fetch Tickets]
    E --> F[Display Tickets]
    D --> G[Show Login Form]
    G --> H{Valid credentials?}
    H -->|Yes| C
    H -->|No| I[Show Error]
    I --> G
```

**Syntax**:

```
flowchart TD
    A[Node] --> B{Decision}
    B -->|Yes| C[Action]
    B -->|No| D[Alternative]
```

### 2. Sequence Diagram

**Use for**: API interactions, request/response flows, authentication flows

```mermaid
sequenceDiagram
    actor User
    participant Frontend
    participant API
    participant Keycloak
    participant Database

    User->>Frontend: Click Login
    Frontend->>Keycloak: POST /token (credentials)
    Keycloak-->>Frontend: JWT Token
    Frontend->>API: GET /tickets (with JWT)
    API->>Keycloak: Validate JWT
    Keycloak-->>API: Token Valid
    API->>Database: SELECT * FROM tickets
    Database-->>API: Ticket rows
    API-->>Frontend: Ticket JSON
    Frontend-->>User: Display Tickets
```

**Syntax**:

```
sequenceDiagram
    participant A
    participant B
    A->>B: Request
    B-->>A: Response
    Note over A,B: Async operation
```

### 3. Class Diagram (ERD)

**Use for**: Database schemas, TypeScript types, domain models

```mermaid
classDiagram
    class Organization {
        +UUID id
        +String name
        +String slug
        +DateTime createdAt
        +projects() Project[]
    }

    class Project {
        +UUID id
        +UUID organizationId
        +String name
        +String key
        +tickets() Ticket[]
    }

    class Ticket {
        +UUID id
        +UUID projectId
        +String title
        +String status
        +UUID assigneeId
        +comments() Comment[]
    }

    class User {
        +UUID id
        +String email
        +String keycloakId
    }

    Organization "1" --> "*" Project : has
    Project "1" --> "*" Ticket : contains
    Ticket "*" --> "1" User : assigned to
```

**Syntax**:

```
classDiagram
    class Entity {
        +Type field
        +method() ReturnType
    }
    Entity "1" --> "*" RelatedEntity : relationship
```

### 4. State Diagram

**Use for**: Ticket workflows, order states, approval processes

```mermaid
stateDiagram-v2
    [*] --> Backlog
    Backlog --> Todo : Prioritize
    Todo --> InProgress : Start Work
    InProgress --> InReview : Submit PR
    InReview --> InProgress : Changes Requested
    InReview --> Done : PR Approved
    InProgress --> Blocked : Dependency Issue
    Blocked --> InProgress : Issue Resolved
    Done --> [*]
```

**Syntax**:

```
stateDiagram-v2
    [*] --> State1
    State1 --> State2 : event
    State2 --> [*]
```

### 5. Entity Relationship Diagram

**Use for**: Database table relationships

```mermaid
erDiagram
    ORGANIZATION ||--o{ PROJECT : "has"
    PROJECT ||--o{ TICKET : "contains"
    TICKET }o--|| USER : "assigned to"
    TICKET ||--o{ COMMENT : "has"
    USER ||--o{ COMMENT : "authored"
    ORGANIZATION ||--o{ USER : "member"

    ORGANIZATION {
        uuid id PK
        string name
        string slug UK
        timestamp created_at
    }

    PROJECT {
        uuid id PK
        uuid organization_id FK
        string name
        string key UK
    }

    TICKET {
        uuid id PK
        uuid project_id FK
        uuid assignee_id FK
        string title
        text description
        enum status
        int priority
    }

    USER {
        uuid id PK
        string email UK
        string keycloak_id UK
    }

    COMMENT {
        uuid id PK
        uuid ticket_id FK
        uuid author_id FK
        text content
        timestamp created_at
    }
```

**Syntax**:

```
erDiagram
    TABLE1 ||--o{ TABLE2 : "relationship"
    TABLE1 {
        type column
    }
```

### 6. Gitgraph (Branch Visualization)

**Use for**: Explaining git workflows, branching strategies

```mermaid
gitgraph
    commit id: "Initial"
    branch develop
    checkout develop
    commit id: "Setup"
    branch feature/EV-123
    checkout feature/EV-123
    commit id: "Implement"
    commit id: "Tests"
    checkout develop
    merge feature/EV-123
    checkout main
    merge develop tag: "v1.0.0"
```

### 7. Gantt Chart

**Use for**: Project timelines, sprint planning

```mermaid
gantt
    title Implementation Timeline
    dateFormat  YYYY-MM-DD
    section Phase 1
    Setup AI-Store           :done, 2026-03-01, 3d
    Stack Detection         :active, 2026-03-04, 5d
    section Phase 2
    Initialize-Project      :2026-03-09, 7d
    Agent Generation        :2026-03-16, 7d
    section Phase 3
    Implement-Ticket        :2026-03-23, 10d
```

## Best Practices

### 1. Keep It Simple

- Maximum 10-15 nodes per diagram
- Use subgraphs for grouping (flowcharts)
- Break complex flows into multiple diagrams

### 2. Use Consistent Naming

- `camelCase` for internal entities
- `PascalCase` for classes/types
- `snake_case` for database columns

### 3. Add Context

- Include a title/heading above diagram
- Explain what the diagram shows
- Link to related documentation

### 4. Color Coding (Optional)

```
style NodeA fill:#f9f,stroke:#333,stroke-width:2px
style NodeB fill:#bbf,stroke:#333,stroke-width:2px
```

### 5. Notes and Annotations

```
Note over User,API: Authentication flow
Note right of API: Validates JWT
```

## Integration with Pull Requests

When creating a PR with architectural changes:

1. **Analyze Changes**: Identify affected components
2. **Choose Diagram Type**:
   - New API endpoints → Sequence diagram
   - Database changes → ERD
   - Complex logic → Flowchart
   - Service interaction → Component diagram
3. **Generate Diagram**: Use Mermaid syntax
4. **Add to PR Description**:

   ````markdown
   ## Architecture

   ### Data Flow

   ```mermaid
   flowchart LR
       A[Client] --> B[API]
       B --> C[Database]
   ```
   ````

   ```

   ```

5. **Explain Context**: Add 2-3 sentences describing the diagram

## Example: PR with Mermaid

````markdown
# Add Real-Time Ticket Updates

## Changes

- Implemented Socket.IO for ticket updates
- Added BullMQ queue for event distribution
- Updated frontend to subscribe to ticket events

## Architecture

### Real-Time Update Flow

```mermaid
sequenceDiagram
    participant User1
    participant Frontend1
    participant API
    participant BullMQ
    participant Socket.IO
    participant Frontend2
    participant User2

    User1->>Frontend1: Update Ticket
    Frontend1->>API: PATCH /tickets/:id
    API->>BullMQ: Publish ticket.updated
    API-->>Frontend1: 200 OK
    BullMQ->>Socket.IO: Process Event
    Socket.IO->>Frontend2: Emit ticket.updated
    Frontend2->>User2: Show Notification
```
````

This diagram shows how ticket updates are propagated in real-time using BullMQ and Socket.IO.

### Database Schema Changes

```mermaid
erDiagram
    TICKET ||--o{ TICKET_EVENT : "has"
    USER ||--o{ TICKET_EVENT : "triggered"

    TICKET_EVENT {
        uuid id PK
        uuid ticket_id FK
        uuid user_id FK
        string event_type
        jsonb payload
        timestamp created_at
    }
```

Added `ticket_events` table to store audit log of all ticket changes.

```

## Mermaid Live Editor

Test diagrams at: https://mermaid.live

## Limitations

- GitHub renders Mermaid automatically
- Some Jira flavors may not support Mermaid (use images)
- Complex diagrams may be slow to render

## Alternative: PlantUML

If Mermaid doesn't support your use case, consider PlantUML for:
- Deployment diagrams
- Component diagrams
- Timing diagrams

## References

- Mermaid Docs: https://mermaid.js.org/
- Syntax Cheat Sheet: https://mermaid.js.org/syntax/
- Live Editor: https://mermaid.live
```
