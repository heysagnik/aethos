import { Text } from "@cloudflare/kumo";
import { SealCheckIcon } from "@phosphor-icons/react";

export function Brand() {
  return (
    <span className="inline-flex items-center gap-2">
      <SealCheckIcon size={22} weight="fill" className="text-kumo-brand" aria-hidden="true" />
      <Text variant="heading" as="span">
        Aethos
      </Text>
    </span>
  );
}
