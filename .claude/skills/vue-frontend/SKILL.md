---
name: vue-frontend
description: Comprehensive Vue.js 3 expertise covering Composition API, Pinia state management, Vue Router, and modern component patterns
---

# Vue Frontend Development

Expert guidance for building modern web applications with Vue 3, focusing on Composition API and best practices.

## Vue 3 Fundamentals

### Composition API with `<script setup>`

```vue
<script setup>
import { ref, computed, onMounted } from 'vue';

// Reactive state
const count = ref(0);
const name = ref('Alice');

// Computed property
const doubleCount = computed(() => count.value * 2);

// Methods
function increment() {
  count.value++;
}

// Lifecycle hook
onMounted(() => {
  console.log('Component mounted');
});
</script>

<template>
  <div>
    <p>Count: {{ count }}</p>
    <p>Double: {{ doubleCount }}</p>
    <button @click="increment">Increment</button>
  </div>
</template>
```

### Reactive State (ref vs reactive)

```vue
<script setup>
import { ref, reactive } from 'vue';

// ref - for primitives and single values
const count = ref(0);
const name = ref('Alice');
count.value++; // Need .value in script

// reactive - for objects
const state = reactive({
  count: 0,
  name: 'Alice',
});
state.count++; // No .value needed

// Common pattern: reactive object with multiple refs
const user = reactive({
  name: ref('Alice'),
  age: ref(30),
});
</script>

<template>
  <!-- No .value needed in template -->
  <p>{{ count }}</p>
  <p>{{ state.name }}</p>
</template>
```

### Computed Properties

```vue
<script setup>
import { ref, computed } from 'vue';

const firstName = ref('John');
const lastName = ref('Doe');

// Read-only computed
const fullName = computed(() => `${firstName.value} ${lastName.value}`);

// Writable computed
const fullNameWritable = computed({
  get() {
    return `${firstName.value} ${lastName.value}`;
  },
  set(newValue) {
    const parts = newValue.split(' ');
    firstName.value = parts[0];
    lastName.value = parts[1];
  },
});
</script>
```

### Lifecycle Hooks

```vue
<script setup>
import {
  onMounted,
  onUpdated,
  onUnmounted,
  onBeforeMount,
  onBeforeUpdate,
  onBeforeUnmount,
} from 'vue';

onBeforeMount(() => {
  console.log('Before component mounts');
});

onMounted(() => {
  console.log('Component mounted');
  // Setup side effects, fetch data, etc.
});

onUpdated(() => {
  console.log('Component updated');
});

onBeforeUnmount(() => {
  console.log('Before component unmounts');
  // Cleanup event listeners, timers, etc.
});

onUnmounted(() => {
  console.log('Component unmounted');
});
</script>
```

### Template Syntax and Directives

```vue
<template>
  <!-- Text interpolation -->
  <p>Message: {{ message }}</p>

  <!-- Raw HTML (use with caution) -->
  <div v-html="rawHtml"></div>

  <!-- Attribute binding -->
  <img :src="imageUrl" :alt="description" />
  <div :class="{ active: isActive, 'text-bold': isBold }"></div>
  <div :style="{ color: textColor, fontSize: fontSize + 'px' }"></div>

  <!-- Conditional rendering -->
  <div v-if="type === 'A'">Type A</div>
  <div v-else-if="type === 'B'">Type B</div>
  <div v-else>Not A or B</div>

  <!-- Show/hide (keeps in DOM) -->
  <div v-show="isVisible">Visible content</div>

  <!-- List rendering -->
  <ul>
    <li v-for="(item, index) in items" :key="item.id">
      {{ index }}: {{ item.name }}
    </li>
  </ul>

  <!-- Event handling -->
  <button @click="handleClick">Click me</button>
  <button @click="count++">Increment</button>
  <input @keyup.enter="submit" />
  <form @submit.prevent="onSubmit">
    <button type="submit">Submit</button>
  </form>

  <!-- Two-way binding -->
  <input v-model="message" />
  <input v-model.number="age" />
  <input v-model.lazy="text" />
  <input v-model.trim="username" />
</template>
```

### Props and Emits

```vue
<!-- Child Component -->
<script setup>
import { computed } from 'vue';

// Define props with types and defaults
const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  count: {
    type: Number,
    default: 0,
  },
  user: {
    type: Object,
    required: true,
  },
});

// Define emits
const emit = defineEmits(['update:count', 'delete']);

function increment() {
  emit('update:count', props.count + 1);
}

function remove() {
  emit('delete', props.user.id);
}
</script>

<!-- Parent Component -->
<template>
  <ChildComponent
    :title="pageTitle"
    :count="counter"
    :user="currentUser"
    @update:count="counter = $event"
    @delete="handleDelete"
  />

  <!-- v-model shorthand for update:modelValue -->
  <CustomInput v-model="text" />
  <!-- Equivalent to: -->
  <CustomInput :modelValue="text" @update:modelValue="text = $event" />
</template>
```

## State Management (Pinia)

### Store Setup

```typescript
// stores/user.ts
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

export const useUserStore = defineStore('user', () => {
  // State
  const user = ref(null);
  const token = ref(localStorage.getItem('token'));

  // Getters
  const isAuthenticated = computed(() => !!token.value);
  const userName = computed(() => user.value?.name ?? 'Guest');

  // Actions
  async function login(credentials) {
    try {
      const response = await api.post('/login', credentials);
      user.value = response.data.user;
      token.value = response.data.token;
      localStorage.setItem('token', token.value);
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  }

  function logout() {
    user.value = null;
    token.value = null;
    localStorage.removeItem('token');
  }

  return { user, token, isAuthenticated, userName, login, logout };
});
```

### Using Stores in Components

```vue
<script setup>
import { useUserStore } from '@/stores/user';
import { storeToRefs } from 'pinia';

const userStore = useUserStore();

// Extract reactive state (preserves reactivity)
const { user, isAuthenticated } = storeToRefs(userStore);

// Actions can be destructured directly
const { login, logout } = userStore;

async function handleLogin() {
  await login({ email: 'user@example.com', password: 'secret' });
}
</script>

<template>
  <div v-if="isAuthenticated">
    <p>Welcome, {{ user.name }}</p>
    <button @click="logout">Logout</button>
  </div>
  <div v-else>
    <button @click="handleLogin">Login</button>
  </div>
</template>
```

### Store Composition

```typescript
// stores/cart.ts
import { defineStore } from 'pinia';
import { useUserStore } from './user';

export const useCartStore = defineStore('cart', () => {
  const userStore = useUserStore();

  const items = ref([]);

  const total = computed(() =>
    items.value.reduce((sum, item) => sum + item.price * item.quantity, 0),
  );

  async function checkout() {
    if (!userStore.isAuthenticated) {
      throw new Error('Must be logged in');
    }
    // Checkout logic
  }

  return { items, total, checkout };
});
```

## Routing (Vue Router 4)

### Route Configuration

```typescript
// router/index.ts
import { createRouter, createWebHistory } from 'vue-router';
import Home from '@/views/Home.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: Home,
    },
    {
      path: '/about',
      name: 'about',
      // Lazy-loaded route
      component: () => import('@/views/About.vue'),
    },
    {
      path: '/users/:id',
      name: 'user-detail',
      component: () => import('@/views/UserDetail.vue'),
      props: true, // Pass route params as props
    },
    {
      path: '/dashboard',
      component: () => import('@/layouts/DashboardLayout.vue'),
      children: [
        {
          path: '',
          name: 'dashboard-home',
          component: () => import('@/views/Dashboard/Home.vue'),
        },
        {
          path: 'settings',
          name: 'dashboard-settings',
          component: () => import('@/views/Dashboard/Settings.vue'),
        },
      ],
    },
    {
      // 404 catch-all
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFound.vue'),
    },
  ],
});

export default router;
```

### Navigation Guards

```typescript
// Global guards
router.beforeEach((to, from) => {
  const userStore = useUserStore()

  // Redirect to login if not authenticated
  if (to.meta.requiresAuth && !userStore.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // Check permissions
  if (to.meta.role && userStore.user.role !== to.meta.role) {
    return { name: 'forbidden' }
  }
})

// Per-route guards
{
  path: '/admin',
  component: AdminDashboard,
  beforeEnter: (to, from) => {
    if (!hasAdminAccess()) {
      return { name: 'home' }
    }
  }
}
```

### Using Router in Components

```vue
<script setup>
import { useRouter, useRoute } from 'vue-router';

const router = useRouter();
const route = useRoute();

// Access route params
const userId = computed(() => route.params.id);

// Access query params
const page = computed(() => route.query.page);

// Programmatic navigation
function goToUser(id) {
  router.push({ name: 'user-detail', params: { id } });
}

function goBack() {
  router.back();
}
</script>

<template>
  <!-- Declarative navigation -->
  <router-link :to="{ name: 'home' }">Home</router-link>
  <router-link :to="`/users/${user.id}`">User Profile</router-link>

  <!-- RouterView for rendering matched component -->
  <router-view />
</template>
```

## Component Patterns

### Composables (Reusable Logic)

```typescript
// composables/useFetch.ts
import { ref } from 'vue'

export function useFetch(url) {
  const data = ref(null)
  const error = ref(null)
  const loading = ref(false)

  async function fetch() {
    loading.value = true
    try {
      const response = await fetch(url)
      data.value = await response.json()
    } catch (err) {
      error.value = err
    } finally {
      loading.value = false
    }
  }

  return { data, error, loading, fetch }
}

// Usage in component
<script setup>
import { useFetch } from '@/composables/useFetch'

const { data: users, loading, fetch } = useFetch('/api/users')

onMounted(() => {
  fetch()
})
</script>
```

### Provide/Inject (Dependency Injection)

```vue
<!-- Parent Component -->
<script setup>
import { provide, ref } from 'vue';

const theme = ref('dark');

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark';
}

// Provide to all descendants
provide('theme', theme);
provide('toggleTheme', toggleTheme);
</script>

<!-- Descendant Component (any level deep) -->
<script setup>
import { inject } from 'vue';

const theme = inject('theme');
const toggleTheme = inject('toggleTheme');
</script>
```

### Slots and Scoped Slots

```vue
<!-- Parent Component -->
<template>
  <Card>
    <template #header>
      <h2>Card Title</h2>
    </template>

    <template #default>
      <p>Card content goes here</p>
    </template>

    <template #footer>
      <button>Action</button>
    </template>
  </Card>

  <!-- Scoped slot usage -->
  <DataList :items="users">
    <template #item="{ item, index }">
      <div>{{ index }}: {{ item.name }}</div>
    </template>
  </DataList>
</template>

<!-- Card Component -->
<template>
  <div class="card">
    <div class="card-header">
      <slot name="header"></slot>
    </div>
    <div class="card-body">
      <slot></slot>
      <!-- Default slot -->
    </div>
    <div class="card-footer">
      <slot name="footer"></slot>
    </div>
  </div>
</template>

<!-- DataList Component with scoped slot -->
<script setup>
defineProps(['items']);
</script>

<template>
  <div v-for="(item, index) in items" :key="item.id">
    <slot name="item" :item="item" :index="index"></slot>
  </div>
</template>
```

### Teleport

```vue
<script setup>
import { ref } from 'vue';

const showModal = ref(false);
</script>

<template>
  <button @click="showModal = true">Open Modal</button>

  <!-- Teleport to body (outside app root) -->
  <Teleport to="body">
    <div v-if="showModal" class="modal">
      <div class="modal-content">
        <h2>Modal Title</h2>
        <p>Modal content</p>
        <button @click="showModal = false">Close</button>
      </div>
    </div>
  </Teleport>
</template>
```

### KeepAlive (Cache Component State)

```vue
<template>
  <router-view v-slot="{ Component }">
    <keep-alive :max="10">
      <component :is="Component" :key="route.fullPath" />
    </keep-alive>
  </router-view>
</template>
```

## Build Tools (Vite)

### Vite Configuration

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['vue', 'vue-router', 'pinia'],
        },
      },
    },
  },
});
```

### Environment Variables

```bash
# .env
VITE_API_URL=http://localhost:8080/api
VITE_APP_TITLE=My App

# .env.production
VITE_API_URL=https://api.production.com
```

```typescript
// Access in code
const apiUrl = import.meta.env.VITE_API_URL;
```

## Testing

### Unit Testing with Vitest

```typescript
// UserCard.spec.ts
import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import UserCard from './UserCard.vue';

describe('UserCard', () => {
  it('renders user name', () => {
    const wrapper = mount(UserCard, {
      props: {
        user: { id: 1, name: 'Alice' },
      },
    });

    expect(wrapper.text()).toContain('Alice');
  });

  it('emits delete event when button clicked', async () => {
    const wrapper = mount(UserCard, {
      props: {
        user: { id: 1, name: 'Alice' },
      },
    });

    await wrapper.find('button.delete').trigger('click');

    expect(wrapper.emitted('delete')).toBeTruthy();
    expect(wrapper.emitted('delete')[0]).toEqual([1]);
  });
});
```

### Component Testing with Playwright

```typescript
import { test, expect } from '@playwright/test';

test('user can login', async ({ page }) => {
  await page.goto('http://localhost:3000/login');

  await page.fill('input[name="email"]', 'user@example.com');
  await page.fill('input[name="password"]', 'password');
  await page.click('button[type="submit"]');

  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.locator('h1')).toContainText('Dashboard');
});
```

## Best Practices

1. **Composition API**: Prefer `<script setup>` for cleaner, more maintainable code
2. **Reactivity**: Use `ref` for primitives, `reactive` for objects
3. **Composables**: Extract reusable logic into composables
4. **Props**: Always define prop types and defaults
5. **Emits**: Explicitly define all events a component emits
6. **State Management**: Use Pinia for global state, local state for component-specific data
7. **Routing**: Lazy-load routes for better performance
8. **TypeScript**: Use TypeScript for type safety
9. **Testing**: Write unit tests for composables, integration tests for user flows
10. **Performance**: Use `v-show` for frequent toggles, `v-if` for conditional rendering
