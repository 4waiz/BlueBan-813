"use client";
/**
 * Minimal, safe Markdown renderer for the project docs (headings, paragraphs,
 * lists, tables, code blocks, quotes, bold / italic / code / links). It builds
 * React elements and never injects HTML, so a doc cannot run script.
 */
import React from "react";

function inline(text: string, key: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g;
  let last = 0, m: RegExpExecArray | null, i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    const k = `${key}-${i++}`;
    if (t.startsWith("**")) out.push(<b key={k} className="text-ink">{t.slice(2, -2)}</b>);
    else if (t.startsWith("`")) out.push(<code key={k} className="rounded bg-deep px-1 py-0.5 font-mono text-[0.92em] text-cyan">{t.slice(1, -1)}</code>);
    else if (t.startsWith("[")) {
      const mm = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(t);
      const href = mm?.[2] || "#";
      const safe = /^(https?:|mailto:|#|\/)/.test(href) ? href : "#";
      out.push(<a key={k} href={safe} target={safe.startsWith("http") ? "_blank" : undefined} rel="noopener noreferrer" className="text-cyan underline-offset-2 hover:underline">{mm?.[1]}</a>);
    } else out.push(<i key={k}>{t.slice(1, -1)}</i>);
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export default function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0, n = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = `b${n++}`;
    if (!line.trim()) { i++; continue; }
    if (line.startsWith("```")) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i++;
      blocks.push(<pre key={key} className="my-2 overflow-x-auto rounded-md border border-edge bg-deep p-3 font-mono text-[11.5px] leading-relaxed text-muted">{buf.join("\n")}</pre>);
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const lvl = h[1].length;
      const cls = lvl === 1 ? "mt-2 font-display text-[22px] font-bold" : lvl === 2 ? "mt-5 border-b border-edge pb-1 font-display text-[17px] font-bold" : "mt-4 text-[14px] font-bold";
      blocks.push(React.createElement(`h${lvl}`, { key, className: cls }, inline(h[2], key)));
      i++;
      continue;
    }
    if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        const cells = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells);
        i++;
      }
      const [head, ...body] = rows;
      blocks.push(
        <div key={key} className="my-2 overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead><tr className="border-b border-edge">{head?.map((c, j) => <th key={j} className="px-2 py-1.5 text-left font-semibold text-dim">{inline(c, `${key}h${j}`)}</th>)}</tr></thead>
            <tbody>{body.map((r, ri) => <tr key={ri} className="border-b border-edge/50 align-top">{r.map((c, j) => <td key={j} className="px-2 py-1.5 text-muted">{inline(c, `${key}r${ri}c${j}`)}</td>)}</tr>)}</tbody>
          </table>
        </div>);
      continue;
    }
    if (/^\s*([*-]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items: string[] = [];
      while (i < lines.length && (/^\s*([*-]|\d+\.)\s+/.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        if (/^\s*([*-]|\d+\.)\s+/.test(lines[i])) items.push(lines[i].replace(/^\s*([*-]|\d+\.)\s+/, ""));
        else items[items.length - 1] += " " + lines[i].trim();
        i++;
      }
      const L = ordered ? "ol" : "ul";
      blocks.push(React.createElement(L, { key, className: `my-2 space-y-1 pl-5 text-muted ${ordered ? "list-decimal" : "list-disc"}` },
        items.map((it, j) => <li key={j}>{inline(it, `${key}i${j}`)}</li>)));
      continue;
    }
    if (line.startsWith(">")) {
      const buf: string[] = [];
      while (i < lines.length && lines[i].startsWith(">")) buf.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push(<blockquote key={key} className="my-2 border-l-2 border-beam/60 pl-3 italic text-muted">{inline(buf.join(" "), key)}</blockquote>);
      continue;
    }
    const buf: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|\||>|\s*([*-]|\d+\.)\s+)/.test(lines[i])) buf.push(lines[i++]);
    blocks.push(<p key={key} className="my-2 leading-relaxed text-muted">{inline(buf.join(" "), key)}</p>);
  }
  return <div className="text-[13px]">{blocks}</div>;
}
