"use client";

import { useState } from "react";

import { DaftarMaster } from "./daftar-master";
import { FormMaster } from "./form-master";

export function MasterClient({ kdprov }: { kdprov: string }) {
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <div className="space-y-6">
      <FormMaster
        kdprov={kdprov}
        onSelesai={() => setRefreshKey((nilai) => nilai + 1)}
      />
      <DaftarMaster refreshKey={refreshKey} />
    </div>
  );
}
