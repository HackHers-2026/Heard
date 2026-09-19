import { Fragment, type ReactNode } from "react";

function inlineText(value: string): ReactNode[] {
  return value.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    return <Fragment key={`${part}-${index}`}>{part}</Fragment>;
  });
}

export default function RichText({ content }: { content: string }) {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      blocks.push(<h4 key={`heading-${index}`}>{inlineText(heading[2])}</h4>);
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(<li key={`item-${index}`}>{inlineText(lines[index].trim().replace(/^[-*]\s+/, ""))}</li>);
        index += 1;
      }
      blocks.push(<ul key={`list-${index}`}>{items}</ul>);
      continue;
    }

    if (/^\d+[.)]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (index < lines.length && /^\d+[.)]\s+/.test(lines[index].trim())) {
        items.push(<li key={`item-${index}`}>{inlineText(lines[index].trim().replace(/^\d+[.)]\s+/, ""))}</li>);
        index += 1;
      }
      blocks.push(<ol key={`list-${index}`}>{items}</ol>);
      continue;
    }

    blocks.push(<p key={`paragraph-${index}`}>{inlineText(line)}</p>);
    index += 1;
  }

  return <div className="rich-text">{blocks}</div>;
}
