/** «Старт» узел — зелёный пузырь, источник первого перехода. */

"use client";

import { Handle, Position } from "@xyflow/react";

export function StartNode() {
  return (
    <div className="flex items-center justify-center w-16 h-16 rounded-full bg-success text-accent-foreground text-xs font-bold shadow-md select-none">
      Старт
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: "var(--success)", width: 10, height: 10 }}
      />
    </div>
  );
}
