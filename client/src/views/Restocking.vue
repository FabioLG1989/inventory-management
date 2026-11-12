<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div v-if="successOrder" class="success-banner" role="status">
        <span>
          {{ t('restocking.success', {
            orderNumber: successOrder.order_number,
            date: formatDate(successOrder.expected_delivery)
          }) }}
        </span>
        <router-link to="/orders" class="banner-link">{{ t('restocking.viewOrders') }}</router-link>
      </div>
      <div v-if="submitError" class="error-banner" role="alert">{{ submitError }}</div>

      <div class="card budget-card">
        <div class="budget-header">
          <div class="stat-label">{{ t('restocking.budget') }}</div>
          <div class="budget-value">{{ formatMoney(budget) }}</div>
        </div>
        <input
          v-model.number="budget"
          type="range"
          class="budget-slider"
          min="0"
          :max="maxBudget"
          step="500"
          :aria-label="t('restocking.budget')"
        />
        <div class="slider-labels">
          <span>{{ formatMoney(0) }}</span>
          <span>{{ formatMoney(maxBudget) }}</span>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.budget') }}</div>
          <div class="stat-value">{{ formatMoney(budget) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.selectedTotal') }}</div>
          <div class="stat-value">{{ formatMoney(selectedTotal) }}</div>
        </div>
        <div :class="['stat-card', remaining < 0 ? 'danger' : 'success']">
          <div class="stat-label">{{ t('restocking.remaining') }}</div>
          <div class="stat-value">{{ formatMoney(remaining) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.longestLeadTime') }}</div>
          <div class="stat-value">{{ longestLeadTime > 0 ? t('restocking.days', { count: longestLeadTime }) : '-' }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }}</h3>
          <div class="order-action">
            <button class="place-order-btn" :disabled="!canSubmit" @click="placeOrder">
              {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
            </button>
            <span v-if="!canSubmit && disabledHint" class="order-hint">{{ disabledHint }}</span>
          </div>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.include') }}</th>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.forecast') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
                <th>{{ t('restocking.table.quantity') }}</th>
                <th>{{ t('restocking.table.lineCost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.item.item_sku" :class="{ 'row-muted': row.muted }">
                <td>
                  <input
                    type="checkbox"
                    :checked="row.included"
                    :aria-label="t('restocking.table.include')"
                    @change="onToggle(row, $event.target.checked)"
                  />
                </td>
                <td class="nowrap"><strong>{{ row.item.item_sku }}</strong></td>
                <td>
                  {{ translateProductName(row.item.item_name) }}
                  <span v-if="row.showOverBudget" class="badge danger over-badge">
                    {{ t('restocking.overBudget') }}
                  </span>
                </td>
                <td>
                  <span :class="['badge', trendClass(row.item.trend)]">
                    {{ t(`trends.${row.item.trend}`) }}
                  </span>
                </td>
                <td>{{ row.item.forecasted_demand }}</td>
                <td>{{ formatMoney(row.item.unit_cost) }}</td>
                <td>{{ t('restocking.days', { count: row.item.lead_time_days }) }}</td>
                <td>
                  <input
                    type="number"
                    class="qty-input"
                    min="0"
                    step="1"
                    :value="row.quantity"
                    :aria-label="t('restocking.table.quantity')"
                    @change="onQuantity(row, $event.target.value, $event.target)"
                  />
                </td>
                <td><strong>{{ formatMoney(row.lineCents / 100) }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrencyWithDecimals } from '../utils/currency'

const TREND_ORDER = { increasing: 0, stable: 1, decreasing: 2 }

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale, translateProductName } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const budget = ref(0)
    const overrides = ref({})
    const submitting = ref(false)
    const submitError = ref(null)
    const successOrder = ref(null)

    const growth = (f) => {
      if (!f.current_demand) return 0
      return (f.forecasted_demand - f.current_demand) / f.current_demand
    }

    const sortedItems = computed(() => {
      return [...forecasts.value].sort((a, b) => {
        const ta = TREND_ORDER[a.trend] ?? 3
        const tb = TREND_ORDER[b.trend] ?? 3
        if (ta !== tb) return ta - tb
        return growth(b) - growth(a)
      })
    })

    const maxBudget = computed(() => {
      const total = forecasts.value.reduce((sum, f) => sum + f.forecasted_demand * f.unit_cost, 0)
      return Math.ceil(total / 500) * 500
    })

    const toCents = (value) => Math.round(Number(value) * 100)

    const recommendations = computed(() => {
      let remainingCents = toCents(budget.value)
      return sortedItems.value.map(item => {
        const unitCents = toCents(item.unit_cost)
        const affordable = unitCents > 0 ? Math.floor(remainingCents / unitCents) : item.forecasted_demand
        const qty = Math.max(0, Math.min(item.forecasted_demand, affordable))
        remainingCents -= qty * unitCents
        return { item, qty, overBudget: qty < item.forecasted_demand }
      })
    })

    const rows = computed(() => {
      return recommendations.value.map(rec => {
        const override = overrides.value[rec.item.item_sku]
        const quantity = override ? override.quantity : rec.qty
        const included = override ? override.included : rec.qty > 0
        const unitCents = toCents(rec.item.unit_cost)
        return {
          item: rec.item,
          quantity,
          included,
          overBudget: rec.overBudget,
          edited: !!override,
          showOverBudget: rec.qty === 0 && !override,
          muted: rec.qty === 0 && !override,
          lineCents: included ? quantity * unitCents : 0
        }
      })
    })

    const selectedRows = computed(() => rows.value.filter(r => r.included && r.quantity > 0))
    const selectedCents = computed(() => selectedRows.value.reduce((sum, r) => sum + r.lineCents, 0))
    const remainingCents = computed(() => toCents(budget.value) - selectedCents.value)
    const selectedTotal = computed(() => selectedCents.value / 100)
    const remaining = computed(() => remainingCents.value / 100)
    const longestLeadTime = computed(() => {
      return selectedRows.value.reduce((max, r) => Math.max(max, r.item.lead_time_days), 0)
    })

    const canSubmit = computed(() => {
      return selectedRows.value.length > 0 && remainingCents.value >= 0 && !submitting.value
    })

    const disabledHint = computed(() => {
      if (submitting.value) return ''
      if (remainingCents.value < 0) return t('restocking.overBudgetHint')
      if (selectedRows.value.length === 0) return t('restocking.noSelection')
      return ''
    })

    const clearFeedback = () => {
      successOrder.value = null
      submitError.value = null
    }

    // Moving the slider discards manual edits
    watch(budget, () => {
      overrides.value = {}
      clearFeedback()
    })

    const setOverride = (row, patch) => {
      clearFeedback()
      overrides.value = {
        ...overrides.value,
        [row.item.item_sku]: {
          included: row.included,
          quantity: row.quantity,
          ...patch
        }
      }
    }

    const onToggle = (row, checked) => {
      const patch = { included: checked }
      if (checked && row.quantity === 0) patch.quantity = row.item.forecasted_demand
      setOverride(row, patch)
    }

    const onQuantity = (row, raw, el) => {
      const parsed = Math.floor(Number(raw))
      const quantity = Number.isFinite(parsed) && parsed > 0 ? parsed : 0
      if (el) el.value = quantity
      setOverride(row, { quantity })
    }

    const trendClass = (trend) => {
      const map = { increasing: 'success', stable: 'info', decreasing: 'warning' }
      return map[trend] || 'info'
    }

    const formatMoney = (value) => {
      const num = Number(value) || 0
      const abs = Math.abs(num)
      const decimals = Number.isInteger(abs) ? 0 : 2
      const formatted = formatCurrencyWithDecimals(abs, currentCurrency.value, decimals)
      return num < 0 ? `-${formatted}` : formatted
    }

    const formatDate = (dateString) => {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return ''
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return date.toLocaleDateString(locale, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      })
    }

    const placeOrder = async () => {
      if (!canSubmit.value) return
      submitting.value = true
      submitError.value = null
      successOrder.value = null
      try {
        const items = selectedRows.value.map(r => ({
          sku: r.item.item_sku,
          name: r.item.item_name,
          quantity: r.quantity,
          unit_cost: r.item.unit_cost,
          lead_time_days: r.item.lead_time_days
        }))
        successOrder.value = await api.createRestockOrder({ items, budget: budget.value })
        overrides.value = {}
      } catch (err) {
        submitError.value = err.response?.data?.detail || err.message
      } finally {
        submitting.value = false
      }
    }

    const loadForecasts = async () => {
      try {
        loading.value = true
        error.value = null
        forecasts.value = await api.getDemandForecasts()
        budget.value = Math.round(maxBudget.value * 0.5 / 500) * 500
      } catch (err) {
        error.value = 'Failed to load demand forecasts: ' + err.message
      } finally {
        loading.value = false
      }
    }

    onMounted(loadForecasts)

    return {
      t,
      loading,
      error,
      budget,
      maxBudget,
      rows,
      selectedTotal,
      remaining,
      longestLeadTime,
      canSubmit,
      disabledHint,
      submitting,
      submitError,
      successOrder,
      translateProductName,
      trendClass,
      formatMoney,
      formatDate,
      onToggle,
      onQuantity,
      placeOrder
    }
  }
}
</script>

<style scoped>
.nowrap {
  white-space: nowrap;
}

.budget-card {
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.budget-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.budget-value {
  font-size: 2.25rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  outline: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #3b82f6;
  border: 3px solid white;
  box-shadow: 0 0 0 1px #3b82f6, 0 1px 3px rgba(15, 23, 42, 0.3);
}

.budget-slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #3b82f6;
  border: 3px solid white;
  box-shadow: 0 0 0 1px #3b82f6, 0 1px 3px rgba(15, 23, 42, 0.3);
}

.budget-slider:focus-visible {
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.3);
}

.slider-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
  font-size: 0.813rem;
  color: #64748b;
}

.success-banner,
.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.875rem 1rem;
  border-radius: 8px;
  margin-bottom: 1.5rem;
  font-size: 0.875rem;
  font-weight: 500;
}

.success-banner {
  background: #d1fae5;
  border: 1px solid #10b981;
  color: #065f46;
}

.error-banner {
  background: #fee2e2;
  border: 1px solid #ef4444;
  color: #991b1b;
}

.banner-link {
  color: #065f46;
  font-weight: 600;
  text-decoration: underline;
  white-space: nowrap;
}

.order-action {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.order-hint {
  font-size: 0.813rem;
  color: #64748b;
}

.place-order-btn {
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.place-order-btn:hover:not(:disabled) {
  background: #1e293b;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  color: #64748b;
  cursor: not-allowed;
}

.qty-input {
  width: 90px;
  padding: 0.375rem 0.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 0.875rem;
  color: #0f172a;
}

.qty-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.row-muted td {
  opacity: 0.5;
}

.over-badge {
  margin-left: 0.5rem;
}
</style>
