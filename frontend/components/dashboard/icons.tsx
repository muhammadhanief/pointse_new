import type { SVGProps } from "react";

// Ikon garis 1,75 px; bentuknya mengikuti objek nyata di menu, bukan satu set ikon generik.
type Props = SVGProps<SVGSVGElement>;

function Dasar({ children, ...props }: Props) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

export function IkonBeranda(props: Props) {
  return (
    <Dasar {...props}>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V21h14V9.5" />
      <path d="M9.5 21v-6h5v6" />
    </Dasar>
  );
}

export function IkonUnggah(props: Props) {
  return (
    <Dasar {...props}>
      <path d="M4 15.5V20h16v-4.5" />
      <path d="M12 4v11" />
      <path d="m7.5 8.5 4.5-4.5 4.5 4.5" />
    </Dasar>
  );
}

export function IkonPengecekan(props: Props) {
  return (
    <Dasar {...props}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
      <path d="m8.5 11 1.8 1.8 3.2-3.6" />
    </Dasar>
  );
}

export function IkonRekap(props: Props) {
  return (
    <Dasar {...props}>
      <path d="M4 20h16" />
      <path d="M7 20v-8" />
      <path d="M12 20V6" />
      <path d="M17 20v-11" />
    </Dasar>
  );
}

export function IkonEkspor(props: Props) {
  return (
    <Dasar {...props}>
      <path d="M4 15.5V20h16v-4.5" />
      <path d="M12 4v11" />
      <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
    </Dasar>
  );
}

export function IkonMaster(props: Props) {
  return (
    <Dasar {...props}>
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="m3 12 9 5 9-5" />
      <path d="m3 16 9 5 9-5" />
    </Dasar>
  );
}

export function IkonSistem(props: Props) {
  return (
    <Dasar {...props}>
      <path d="M3 12h4l2.5-6 4 12 2.5-6H21" />
      <path d="M4 20h16" />
    </Dasar>
  );
}

export function IkonMenu(props: Props) {
  return (
    <Dasar {...props}>
      <path d="M4 7h16" />
      <path d="M4 12h16" />
      <path d="M4 17h16" />
    </Dasar>
  );
}

export function IkonTutup(props: Props) {
  return (
    <Dasar {...props}>
      <path d="m6 6 12 12" />
      <path d="M18 6 6 18" />
    </Dasar>
  );
}

export function IkonKeluar(props: Props) {
  return (
    <Dasar {...props}>
      <path d="M14 4h5v16h-5" />
      <path d="M10 8 6 12l4 4" />
      <path d="M6 12h9" />
    </Dasar>
  );
}
