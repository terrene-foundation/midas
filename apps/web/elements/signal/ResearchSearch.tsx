"use client";

import { useState } from "react";
import { api } from "@/lib/api-client";
import { cn } from "@/elements/ui/utils";

interface ResearchResult {
  id: string;
  title: string;
  summary: string;
  source: string;
  relevance: number;
  published_at: string;
}

interface ResearchSearchProps {
  className?: string;
}

/**
 * Search bar calling POST /api/v1/signal/research
 */
export function ResearchSearch({ className }: ResearchSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ResearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setHasSearched(true);
    try {
      const response = await api.post<{ results: ResearchResult[] }>(
        "/signal/research",
        { query: query.trim() },
      );
      setResults(response.results ?? []);
    } catch {
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className={cn("space-y-3", className)}>
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search research..."
          className="flex-1 rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
        />
        <button
          type="submit"
          disabled={isSearching || !query.trim()}
          className="px-4 py-2 rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-base)] text-sm font-medium hover:brightness-110 transition-all disabled:opacity-50"
        >
          {isSearching ? "Searching..." : "Search"}
        </button>
      </form>

      {/* Results */}
      {hasSearched && (
        <div className="space-y-2">
          {results.length === 0 && !isSearching && (
            <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 text-center">
              <p className="text-sm text-[var(--text-muted)]">
                No research found for "{query}"
              </p>
            </div>
          )}
          {results.map((result) => (
            <div
              key={result.id}
              className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-2"
            >
              <div className="flex items-start justify-between gap-2">
                <h4 className="text-sm font-medium text-[var(--text-primary)]">
                  {result.title}
                </h4>
                <span
                  className={cn(
                    "text-[10px] font-mono-nums px-2 py-0.5 rounded-full",
                    result.relevance >= 0.7
                      ? "bg-[var(--gain-green)]/20 text-[var(--gain-green)]"
                      : result.relevance >= 0.4
                        ? "bg-[var(--accent-gold)]/20 text-[var(--accent-gold)]"
                        : "bg-[var(--bg-elevated)] text-[var(--text-muted)]",
                  )}
                >
                  {Math.round(result.relevance * 100)}% match
                </span>
              </div>
              <p className="text-xs text-[var(--text-secondary)] line-clamp-2">
                {result.summary}
              </p>
              <div className="flex items-center justify-between text-[10px] text-[var(--text-muted)]">
                <span>{result.source}</span>
                <span>
                  {new Date(result.published_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
