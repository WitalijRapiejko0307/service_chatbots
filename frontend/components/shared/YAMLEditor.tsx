/** Monaco Editor component for YAML editing. */

"use client";

import React, { useRef, useState, useEffect } from "react";
import dynamic from "next/dynamic";

// Dynamically import Monaco Editor to avoid SSR issues
const Editor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[400px] border border-gray-300 rounded-sm bg-gray-50">
      <p className="text-sm text-gray-500">Loading editor...</p>
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

export const YAMLEditor: React.FC<YAMLEditorProps> = ({
  value,
  onChange,
  readOnly = false,
  height = "400px",
  language = "yaml",
  error,
}) => {
  const editorRef = useRef<any>(null);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const handleEditorDidMount = (editor: any) => {
    editorRef.current = editor;
  };

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
            error ? "border-red-500" : "border-gray-300"
          }`}
        >
          <div className="flex items-center justify-center" style={{ height }}>
            <p className="text-sm text-gray-500">Loading editor...</p>
          </div>
        </div>
        {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
      </div>
    );
  }

  return (
    <div className="w-full">
      <div
        className={`border rounded-sm overflow-hidden ${
          error ? "border-red-500" : "border-gray-300"
        }`}
      >
        <Editor
          height={height}
          language={language}
          value={value}
          onChange={handleEditorChange}
          onMount={handleEditorDidMount}
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
          theme="vs"
        />
      </div>
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
    </div>
  );
};


