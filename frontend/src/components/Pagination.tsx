interface PaginationData {
  offset: number;
  limit: number;
  total: number;
  setOffset: (offset: number) => void;
}

export function Pagination({ data }: { data: PaginationData }) {
  const start = data.total ? Math.min(data.offset + 1, data.total) : 0;
  const end = Math.min(data.offset + data.limit, data.total);
  return (
    <nav className="pagination" aria-label="Register pages">
      <button
        type="button"
        disabled={data.offset === 0}
        onClick={() => data.setOffset(Math.max(0, data.offset - data.limit))}
      >
        Previous
      </button>
      <span>{start}-{end} / {data.total}</span>
      <button
        type="button"
        disabled={end >= data.total}
        onClick={() => data.setOffset(data.offset + data.limit)}
      >
        Next
      </button>
    </nav>
  );
}
