import { useEffect, useState } from "react";
import { api, type IntegrationsStatus } from "./api";

/** Read-only connection status for the app shell (sidebar + top bar). Not
 * used for any gating decision — the backend decides that independently,
 * per-action, at the moment it runs. */
export function useIntegrationsStatus(): IntegrationsStatus | null {
  const [status, setStatus] = useState<IntegrationsStatus | null>(null);

  useEffect(() => {
    api.getIntegrationsStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  return status;
}
