import { useEffect, useState } from "react";

/** Load data once on mount. `fn` is read only on the first render. */
export function useLoad<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let on = true;
    fn()
      .then((d) => on && setData(d))
      .catch((e: Error) => on && setError(e.message));
    return () => {
      on = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return { data, error, setData };
}
