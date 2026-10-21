"use client";

import { useState } from "react";

import { FormRekap } from "./form-rekap";
import {
  NotifikasiUnduh,
  type NotifikasiUnduhData,
} from "./notifikasi-unduh";

export function EksporClient() {
  const [notifikasi, setNotifikasi] =
    useState<NotifikasiUnduhData | null>(null);

  function tampilkan(nama: string, status: NotifikasiUnduhData["status"]) {
    setNotifikasi({ nama, status });
  }

  return (
    <>
      <FormRekap
        onMulai={() => tampilkan("Rekap CSV", "menyiapkan")}
        onSiap={(nama) => tampilkan(nama, "mulai")}
        onGagal={() => setNotifikasi(null)}
      />
      {notifikasi ? (
        <NotifikasiUnduh
          data={notifikasi}
          onTutup={() => setNotifikasi(null)}
        />
      ) : null}
    </>
  );
}
