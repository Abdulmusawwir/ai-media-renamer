import { useMemo, useRef, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type RowSelectionState,
  type SortingState,
  type FilterFn,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  Download,
  Upload,
  Save,
  Tag,
  ArrowRight,
} from "lucide-react";
import { type StagedAsset } from "../api/client";
import {
  useStaging,
  useBulkUpdateStaging,
  useImportStagingCsv,
  useSaveStaging,
  downloadStagingCsv,
} from "../hooks/api";
import { useStore, useToast } from "../store";
import { Skeleton, SkeletonRows, Spinner } from "../components/Skeleton";

const PIE_COLORS = [
  "#3b82f6",
  "#22c55e",
  "#f59e0b",
  "#ef4444",
  "#a855f7",
  "#14b8a6",
  "#ec4899",
  "#84cc16",
];

const columnHelper = createColumnHelper<StagedAsset>();

// Case-insensitive match across the most relevant text columns.
const globalFilterFn: FilterFn<StagedAsset> = (row, _columnId, value) => {
  const q = String(value).toLowerCase().trim();
  if (!q) return true;
  const a = row.original;
  const hay = [
    a.original_name,
    a.staged_name,
    a.category,
    (a.tags ?? []).join(" "),
    a.description ?? "",
  ]
    .join(" ")
    .toLowerCase();
  return hay.includes(q);
};

export default function Staging() {
  const navigate = useNavigate();
  const toast = useToast();
  const query = useStaging();
  const categories = useStore((s) => s.categories);
  const bulk = useBulkUpdateStaging();
  const save = useSaveStaging();
  const importCsv = useImportStagingCsv();

  if (query.isLoading) {
    return (
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Staging</h2>
          <p className="text-sm text-text-dim">
            Review and edit AI suggestions before committing to disk.
          </p>
        </div>
        <div className="flex items-center gap-2 px-1 text-sm text-text-dim">
          <Spinner size={16} label="Loading staged assets…" />
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
          <div className="rounded-lg border border-border bg-bg-elev p-4 lg:col-span-3">
            <SkeletonRows rows={6} />
          </div>
          <div className="rounded-lg border border-border bg-bg-elev p-4">
            <Skeleton className="h-48" />
          </div>
        </div>
      </div>
    );
  }

  const serverRows = query.data?.assets ?? [];
  const [rows, setRows] = useState<StagedAsset[]>([]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [bulkCategory, setBulkCategory] = useState<string>("");
  const lastClicked = useRef<number | null>(null);
  const parentRef = useRef<HTMLDivElement>(null);
  const [hoverThumb, setHoverThumb] = useState<{
    src: string;
    x: number;
    y: number;
  } | null>(null);

  // Sync server rows into local editable state when the query resolves.
  const [syncedKey, setSyncedKey] = useState<string>("");
  const key = String(query.dataUpdatedAt);
  if (key !== syncedKey && serverRows.length > 0) {
    setRows(serverRows.map((a) => ({ ...a, tags: a.tags ?? [] })));
    setSyncedKey(key);
  }

  const categoryOptions = useMemo(() => {
    const set = new Set<string>(categories);
    rows.forEach((r) => r.category && set.add(r.category));
    return Array.from(set).sort();
  }, [categories, rows]);

  const updateRow = (idx: number, patch: Partial<StagedAsset>) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };

  const selectedNames = useMemo(
    () =>
      Object.keys(rowSelection)
        .filter((k) => rowSelection[k])
        .map((k) => rows[Number(k)]?.original_name)
        .filter(Boolean) as string[],
    [rowSelection, rows]
  );

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: "select",
        enableSorting: false,
        header: ({ table }) => (
          <input
            type="checkbox"
            checked={table.getIsAllRowsSelected()}
            ref={(el) => {
              if (el) el.indeterminate = table.getIsSomeRowsSelected();
            }}
            onChange={table.getToggleAllRowsSelectedHandler()}
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
          />
        ),
      }),
      columnHelper.accessor("original_name", {
        header: "Original",
        cell: (info) => (
          <span className="text-text-dim">{info.getValue()}</span>
        ),
      }),
      columnHelper.accessor("staged_name", {
        header: "Proposed filename",
        cell: (info) => (
          <input
            className="w-full rounded border border-transparent bg-transparent px-1 py-0.5 text-sm hover:border-border focus:border-accent focus:bg-bg"
            value={info.getValue() ?? ""}
            onChange={(e) =>
              updateRow(info.row.index, { staged_name: e.target.value })
            }
          />
        ),
      }),
      columnHelper.accessor("category", {
        header: "Category",
        cell: (info) => (
          <select
            className="w-full rounded border border-transparent bg-transparent px-1 py-0.5 text-sm hover:border-border focus:border-accent focus:bg-bg"
            value={info.getValue() ?? ""}
            onChange={(e) =>
              updateRow(info.row.index, { category: e.target.value })
            }
          >
            <option value="">—</option>
            {categoryOptions.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        ),
      }),
      columnHelper.accessor("tags", {
        header: "Tags",
        cell: (info) => (
          <input
            className="w-full rounded border border-transparent bg-transparent px-1 py-0.5 text-sm hover:border-border focus:border-accent focus:bg-bg"
            value={(info.getValue() ?? []).join(", ")}
            onChange={(e) =>
              updateRow(info.row.index, {
                tags: e.target.value
                  .split(",")
                  .map((t) => t.trim())
                  .filter(Boolean),
              })
            }
          />
        ),
      }),
      columnHelper.accessor("description", {
        header: "Description",
        cell: (info) => (
          <input
            className="w-full rounded border border-transparent bg-transparent px-1 py-0.5 text-sm hover:border-border focus:border-accent focus:bg-bg"
            value={info.getValue() ?? ""}
            onChange={(e) =>
              updateRow(info.row.index, { description: e.target.value })
            }
          />
        ),
      }),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [categoryOptions, rows]
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { rowSelection, sorting, globalFilter },
    onRowSelectionChange: setRowSelection,
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    globalFilterFn,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getRowId: (_, index) => String(index),
  });

  const visibleRows = table.getRowModel().rows;

  const rowVirtualizer = useVirtualizer({
    count: visibleRows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 44,
    overscan: 12,
  });

  const virtualItems = rowVirtualizer.getVirtualItems();
  const paddingTop = virtualItems.length > 0 ? virtualItems[0].start : 0;
  const paddingBottom =
    virtualItems.length > 0
      ? rowVirtualizer.getTotalSize() -
        virtualItems[virtualItems.length - 1].end
      : 0;

  const handleRowClick = (
    e: React.MouseEvent,
    index: number
  ) => {
    const tag = (e.target as HTMLElement).tagName;
    if (
      tag === "INPUT" ||
      tag === "SELECT" ||
      tag === "BUTTON" ||
      tag === "TEXTAREA"
    ) {
      return;
    }
    const meta = e.metaKey || e.ctrlKey;
    const shift = e.shiftKey;
    setRowSelection((prev) => {
      const next: RowSelectionState = { ...prev };
      if (shift && lastClicked.current !== null) {
        const [a, b] = [lastClicked.current, index].sort((x, y) => x - y);
        for (let i = a; i <= b; i++) next[String(i)] = true;
      } else if (meta) {
        next[String(index)] = !prev[String(index)];
      } else {
        Object.keys(next).forEach((k) => (next[k] = false));
        next[String(index)] = true;
      }
      return next;
    });
    if (!shift) lastClicked.current = index;
  };

  const handleRowEnter = (
    e: React.MouseEvent,
    asset: StagedAsset
  ) => {
    const src = asset.base64_data ?? (asset as { thumbnail?: string }).thumbnail;
    if (typeof src === "string" && src.startsWith("data:image")) {
      setHoverThumb({ src, x: e.clientX, y: e.clientY });
    }
  };

  // Global keyboard hooks: delete selected rows / escape (dismiss hover).
  useEffect(() => {
    const onDelete = () => {
      if (selectedNames.length === 0) {
        toast.info("No rows selected.");
        return;
      }
      setRows((prev) =>
        prev.filter((r) => !selectedNames.includes(r.original_name))
      );
      setRowSelection({});
      lastClicked.current = null;
      toast.success(`Removed ${selectedNames.length} row(s).`);
    };
    const onEscape = () => setHoverThumb(null);
    window.addEventListener("amr:delete-selected", onDelete);
    window.addEventListener("amr:escape", onEscape);
    return () => {
      window.removeEventListener("amr:delete-selected", onDelete);
      window.removeEventListener("amr:escape", onEscape);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNames, toast]);

  const applyBulk = async () => {
    if (selectedNames.length === 0 || !bulkCategory) {
      toast.error("Select rows and choose a category first.");
      return;
    }
    try {
      const res = await bulk.mutateAsync({
        selected: selectedNames,
        updates: { category: bulkCategory },
      });
      toast.success(`Applied category to ${res.applied} asset(s).`);
      setRows((prev) =>
        prev.map((r) =>
          selectedNames.includes(r.original_name)
            ? { ...r, category: bulkCategory }
            : r
        )
      );
    } catch (err) {
      toast.error(String(err));
    }
  };

  const onSave = async () => {
    try {
      const clean = rows.map(({ selected: _s, ...rest }) => rest) as StagedAsset[];
      await save.mutateAsync(clean);
      toast.success("Staging saved.");
    } catch (err) {
      toast.error(String(err));
    }
  };

  const onImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const csv = await file.text();
      const res = await importCsv.mutateAsync(csv);
      toast.success(`Imported ${res.imported} asset(s).`);
      setRowSelection({});
    } catch (err) {
      toast.error(String(err));
    }
  };

  const chartData = useMemo(() => {
    const counts = new Map<string, number>();
    rows.forEach((r) => {
      const c = r.category || "uncategorized";
      counts.set(c, (counts.get(c) ?? 0) + 1);
    });
    return Array.from(counts.entries()).map(([name, value]) => ({
      name,
      value,
    }));
  }, [rows]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Staging</h2>
          <p className="text-sm text-text-dim">
            Review and edit AI suggestions before committing to disk.
          </p>
        </div>
        <button
          className="flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-2"
          onClick={() => navigate("/commit")}
        >
          Go to Commit <ArrowRight size={16} />
        </button>
      </div>

      {query.isError && (
        <div className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          Failed to load staging: {String(query.error)}
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-bg-elev p-3">
        <select
          className="rounded-md border border-border bg-bg px-3 py-1.5 text-sm"
          value={bulkCategory}
          onChange={(e) => setBulkCategory(e.target.value)}
        >
          <option value="">Bulk category…</option>
          {categoryOptions.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <button
          className="flex items-center gap-1.5 rounded-md border border-border bg-bg-elev-2 px-3 py-1.5 text-sm hover:bg-bg"
          onClick={applyBulk}
          disabled={bulk.isPending}
        >
          <Tag size={14} /> Apply to selected
        </button>
        <span className="text-xs text-text-dim">
          {selectedNames.length} selected
        </span>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            placeholder="Filter by name / category / tag / description…"
            className="w-56 rounded-md border border-border bg-bg px-3 py-1.5 text-sm placeholder:text-text-dim"
          />
          <button
            className="flex items-center gap-1.5 rounded-md border border-border bg-bg-elev-2 px-3 py-1.5 text-sm hover:bg-bg"
            onClick={onSave}
            disabled={save.isPending}
          >
            <Save size={14} /> Save
          </button>
          <button
            className="flex items-center gap-1.5 rounded-md border border-border bg-bg-elev-2 px-3 py-1.5 text-sm hover:bg-bg"
            onClick={downloadStagingCsv}
          >
            <Download size={14} /> Export CSV
          </button>
          <label className="flex cursor-pointer items-center gap-1.5 rounded-md border border-border bg-bg-elev-2 px-3 py-1.5 text-sm hover:bg-bg">
            <Upload size={14} /> Import CSV
            <input
              type="file"
              accept=".csv"
              className="hidden"
              onChange={onImport}
            />
          </label>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        {/* Table */}
        <div
          ref={parentRef}
          className="max-h-[600px] overflow-auto rounded-lg border border-border bg-bg-elev lg:col-span-3"
        >
          <table className="w-full border-collapse text-sm">
            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id} className="border-b border-border">
                  {hg.headers.map((h) => {
                    const canSort = h.column.getCanSort();
                    const sorted = h.column.getIsSorted();
                    return (
                      <th
                        key={h.id}
                        className="sticky top-0 z-10 bg-bg-elev px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-text-dim"
                      >
                        <button
                          type="button"
                          disabled={!canSort}
                          onClick={canSort ? h.column.getToggleSortingHandler() : undefined}
                          className={`flex items-center gap-1 ${
                            canSort ? "cursor-pointer hover:text-text" : "cursor-default"
                          }`}
                        >
                          {flexRender(h.column.columnDef.header, h.getContext())}
                          {sorted === "asc" && <span>▲</span>}
                          {sorted === "desc" && <span>▼</span>}
                          {canSort && !sorted && <span className="opacity-40">↕</span>}
                        </button>
                      </th>
                    );
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {paddingTop > 0 && (
                <tr aria-hidden>
                  <td colSpan={columns.length} style={{ height: paddingTop }} />
                </tr>
              )}
              {virtualItems.map((vi) => {
                const row = visibleRows[vi.index];
                return (
                  <tr
                    key={row.id}
                    className={`border-b border-border/60 hover:bg-bg-elev-2 ${
                      row.getIsSelected() ? "bg-accent/10" : ""
                    }`}
                    onClick={(e) => handleRowClick(e, row.index)}
                    onMouseEnter={(e) => handleRowEnter(e, row.original)}
                    onMouseMove={(e) =>
                      setHoverThumb((prev) =>
                        prev
                          ? { ...prev, x: e.clientX, y: e.clientY }
                          : prev
                      )
                    }
                    onMouseLeave={() => setHoverThumb(null)}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-1.5 align-top">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                );
              })}
              {paddingBottom > 0 && (
                <tr aria-hidden>
                  <td colSpan={columns.length} style={{ height: paddingBottom }} />
                </tr>
              )}
              {visibleRows.length === 0 && (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="px-3 py-6 text-center text-text-dim"
                  >
                    No staged assets. Run an analysis first.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Analytics */}
        <div className="rounded-lg border border-border bg-bg-elev p-4">
          <div className="mb-2 text-sm font-medium text-text-dim">
            Category distribution
          </div>
          {chartData.length === 0 ? (
            <div className="py-10 text-center text-xs text-text-dim">
              No data
            </div>
          ) : (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={chartData}
                    dataKey="value"
                    nameKey="name"
                    outerRadius={70}
                    label={(e: { name?: string; percent?: number }) =>
                      `${e.name} ${Math.round((e.percent ?? 0) * 100)}%`
                    }
                  >
                    {chartData.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: "#171a21",
                      border: "1px solid #2a2f3a",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {hoverThumb && (
        <div
          className="pointer-events-none fixed z-50 w-48 rounded-md border border-border bg-bg-elev p-1 shadow-lg"
          style={{
            left: Math.min(hoverThumb.x + 12, window.innerWidth - 200),
            top: Math.min(hoverThumb.y + 12, window.innerHeight - 200),
          }}
        >
          <img
            src={hoverThumb.src}
            alt="preview"
            className="h-40 w-full rounded object-contain"
          />
        </div>
      )}
    </div>
  );
}
