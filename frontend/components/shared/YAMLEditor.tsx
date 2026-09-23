/** Monaco Editor component for YAML editing. */

"use client";

import React, { useSyncExternalStore } from "react";
import dynamic from "next/dynamic";
import { useTheme } from "next-themes";
// Dynamically import Monaco Editor to avoid SSR issues
const Editor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[400px] border border-border rounded-sm bg-surface">
      <p className="text-sm text-muted">Loading editor...</p>
    </div>
  ),
});

interface YAMLEditorProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  height?: string;
  language?: string;
  error?: string;
}

const subscribeToClientMount = () => () => {};
const getClientMounted = () => true;
const getServerMounted = () => false;

export const YAMLEditor: React.FC<YAMLEditorProps> = ({
  value,
  onChange,
  readOnly = false,
  height = "400px",
  language = "yaml",
  error,
}) => {
  const isMounted = useSyncExternalStore(
    subscribeToClientMount,
    getClientMounted,
    getServerMounted
  );
  const { resolvedTheme } = useTheme();
  const monacoTheme = resolvedTheme === "dark" ? "vs-dark" : "vs";

  const handleEditorChange = (value: string | undefined) => {
    if (onChange && value !== undefined) {
      onChange(value);
    }
  };

  if (!isMounted) {
    return (
      <div className="w-full">
        <div
          className={`border rounded-sm overflow-hidden ${
            error ? "border-danger" : "border-border"
          }`}
        >
          <div className="flex items-center justify-center" style={{ height }}>
            <p className="text-sm text-muted">Loading editor...</p>
          </div>
        </div>
        {error && <p className="mt-1 text-sm text-danger">{error}</p>}
      </div>
    );
  }

  return (
    <div className="w-full">
      <div
        className={`border rounded-sm overflow-hidden ${
          error ? "border-danger" : "border-border"
        }`}
      >
        <Editor
          height={height}
          language={language}
          value={value}
          onChange={handleEditorChange}
          options={{
            readOnly,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            fontSize: 14,
            lineNumbers: "on",
            wordWrap: "on",
            automaticLayout: true,
            tabSize: 2,
            formatOnPaste: true,
            formatOnType: true,
          }}
          theme={monacoTheme}
        />
      </div>
      {error && <p className="mt-1 text-sm text-danger">{error}</p>}
    </div>
  );
};
