import { SealCheckIcon } from "@phosphor-icons/react";

export function Brand() {
  return (
    <span className="inline-flex items-center gap-2">
      <SealCheckIcon size={22} weight="fill" className="text-orange-500" aria-hidden="true" />
      <span className="text-base font-semibold">Aethos</span>
    </span>
  );
}
