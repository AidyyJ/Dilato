"use client";

import { useEffect, useState } from "react";
import { api, PricingRule, PricingRuleCreate, RuleType } from "@/lib/api";

const ruleTypes: RuleType[] = ["fixed_markup", "percentage", "fixed_price"];

export default function PricingPage() {
  const [rules, setRules] = useState<PricingRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<PricingRule | null>(null);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    api.pricing
      .listRules()
      .then((data) => {
        setRules(data);
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load rules");
        setLoading(false);
      });
  }, []);

  async function handleDelete(id: number) {
    if (!confirm("Are you sure you want to delete this pricing rule?")) return;
    try {
      await api.pricing.deleteRule(id);
      setRules((prev) => prev.filter((r) => r.id !== id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function toggleActive(rule: PricingRule) {
    try {
      const updated = await api.pricing.updateRule(rule.id, { is_active: !rule.is_active });
      setRules((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Pricing Rules</h1>
          <p className="text-neutral-600 dark:text-neutral-400 mt-1">
            Configure margin and markup rules that apply to listings.
          </p>
        </div>
        <button
          onClick={() => {
            setEditing(null);
            setShowForm(true);
          }}
          className="inline-flex items-center justify-center px-4 py-2 rounded-md bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 text-sm font-medium hover:bg-neutral-800 dark:hover:bg-neutral-200 transition-colors"
        >
          Add Rule
        </button>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {showForm && (
        <RuleForm
          initial={editing}
          onClose={() => setShowForm(false)}
          onSaved={(rule) => {
            if (editing) {
              setRules((prev) => prev.map((r) => (r.id === rule.id ? rule : r)));
            } else {
              setRules((prev) => [...prev, rule]);
            }
            setShowForm(false);
            setEditing(null);
          }}
        />
      )}

      <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-neutral-50 dark:bg-neutral-900 text-neutral-700 dark:text-neutral-300">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Name</th>
                <th className="px-4 py-3 text-left font-medium">Type</th>
                <th className="px-4 py-3 text-left font-medium">Value</th>
                <th className="px-4 py-3 text-left font-medium">Min Price</th>
                <th className="px-4 py-3 text-left font-medium">Max Price</th>
                <th className="px-4 py-3 text-left font-medium">Min Margin %</th>
                <th className="px-4 py-3 text-left font-medium">Priority</th>
                <th className="px-4 py-3 text-left font-medium">Active</th>
                <th className="px-4 py-3 text-left font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {loading ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-neutral-500">
                    Loading…
                  </td>
                </tr>
              ) : rules.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-neutral-500">
                    No pricing rules found.
                  </td>
                </tr>
              ) : (
                rules.map((r) => (
                  <tr key={r.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-900/50">
                    <td className="px-4 py-3 font-medium">{r.name}</td>
                    <td className="px-4 py-3">{r.rule_type}</td>
                    <td className="px-4 py-3">{r.value}</td>
                    <td className="px-4 py-3">{r.min_price ?? "—"}</td>
                    <td className="px-4 py-3">{r.max_price ?? "—"}</td>
                    <td className="px-4 py-3">{r.min_margin_percent ?? "—"}</td>
                    <td className="px-4 py-3">{r.priority}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => toggleActive(r)}
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium transition-colors ${
                          r.is_active
                            ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
                            : "bg-neutral-100 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-300"
                        }`}
                      >
                        {r.is_active ? "Yes" : "No"}
                      </button>
                    </td>
                    <td className="px-4 py-3 space-x-3">
                      <button
                        onClick={() => {
                          setEditing(r);
                          setShowForm(true);
                        }}
                        className="text-sm text-neutral-700 dark:text-neutral-300 hover:underline"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(r.id)}
                        className="text-sm text-red-600 dark:text-red-400 hover:underline"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function RuleForm({
  initial,
  onClose,
  onSaved,
}: {
  initial: PricingRule | null;
  onClose: () => void;
  onSaved: (rule: PricingRule) => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [ruleType, setRuleType] = useState<RuleType>(initial?.rule_type ?? "fixed_markup");
  const [value, setValue] = useState(initial?.value ?? "");
  const [minPrice, setMinPrice] = useState(initial?.min_price ?? "");
  const [maxPrice, setMaxPrice] = useState(initial?.max_price ?? "");
  const [minMargin, setMinMargin] = useState(initial?.min_margin_percent ?? "");
  const [priority, setPriority] = useState(String(initial?.priority ?? 0));
  const [isActive, setIsActive] = useState(initial?.is_active ?? true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);

    const payload: PricingRuleCreate = {
      name,
      rule_type: ruleType,
      value,
      priority: Number(priority) || 0,
      is_active: isActive,
    };
    if (minPrice) payload.min_price = minPrice;
    if (maxPrice) payload.max_price = maxPrice;
    if (minMargin) payload.min_margin_percent = minMargin;

    try {
      if (initial) {
        const updated = await api.pricing.updateRule(initial.id, payload);
        onSaved(updated);
      } else {
        const created = await api.pricing.createRule(payload);
        onSaved(created);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-5 space-y-4">
      <h2 className="font-semibold">{initial ? "Edit Rule" : "New Rule"}</h2>
      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}
      <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="sm:col-span-2 lg:col-span-3">
          <label htmlFor="rule-name" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">Name</label>
          <input
            id="rule-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
          />
        </div>
        <div>
          <label htmlFor="rule-type" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">Type</label>
          <select
            id="rule-type"
            value={ruleType}
            onChange={(e) => setRuleType(e.target.value as RuleType)}
            required
            className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
          >
            {ruleTypes.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="rule-value" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">Value</label>
          <input
            id="rule-value"
            type="number"
            step="0.01"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            required
            className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
          />
        </div>
        <div>
          <label htmlFor="rule-priority" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">Priority</label>
          <input
            id="rule-priority"
            type="number"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            required
            className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
          />
        </div>
        <div>
          <label htmlFor="rule-min-price" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">Min Price</label>
          <input
            id="rule-min-price"
            type="number"
            step="0.01"
            value={minPrice}
            onChange={(e) => setMinPrice(e.target.value)}
            className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
          />
        </div>
        <div>
          <label htmlFor="rule-max-price" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">Max Price</label>
          <input
            id="rule-max-price"
            type="number"
            step="0.01"
            value={maxPrice}
            onChange={(e) => setMaxPrice(e.target.value)}
            className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
          />
        </div>
        <div>
          <label htmlFor="rule-min-margin" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">Min Margin %</label>
          <input
            id="rule-min-margin"
            type="number"
            step="0.01"
            value={minMargin}
            onChange={(e) => setMinMargin(e.target.value)}
            className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-400"
          />
        </div>
        <div className="flex items-center gap-2">
          <input
            id="is-active"
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="h-4 w-4 rounded border-neutral-300 text-neutral-900 focus:ring-neutral-400"
          />
          <label htmlFor="is-active" className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
            Active
          </label>
        </div>
        <div className="sm:col-span-2 lg:col-span-3 flex items-center gap-3 pt-2">
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center justify-center px-4 py-2 rounded-md bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 text-sm font-medium hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-50 transition-colors"
          >
            {saving ? "Saving…" : initial ? "Update Rule" : "Create Rule"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center justify-center px-4 py-2 rounded-md border border-neutral-300 dark:border-neutral-700 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-900 transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
