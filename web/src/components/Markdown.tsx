import { Children, isValidElement, useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import rehypeSlug from 'rehype-slug'
import { Alert, Skeleton } from 'antd'
import { Link, useLocation } from 'react-router-dom'
import { resolveDocumentLink } from '../content'

let diagramNumber = 0

function MermaidDiagram({ code }: { code: string }) {
  const [svg, setSvg] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    const id = `research-diagram-${++diagramNumber}`
    setSvg('')
    setError('')
    import('mermaid').then(async ({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'base',
        fontFamily: 'system-ui, "Noto Sans CJK SC", sans-serif',
        themeVariables: {
          darkMode: true,
          background: '#181825',
          primaryColor: '#313244',
          primaryTextColor: '#cdd6f4',
          primaryBorderColor: '#cba6f7',
          secondaryColor: '#45475a',
          tertiaryColor: '#1e1e2e',
          lineColor: '#a6adc8',
          textColor: '#cdd6f4',
          edgeLabelBackground: '#181825',
        },
      })
      const result = await mermaid.render(id, code)
      if (active) setSvg(result.svg)
    }).catch(() => {
      if (active) setError('此图未能渲染，可查看下方的原始内容。')
    })
    return () => { active = false }
  }, [code])

  if (error) return <><Alert type="warning" title={error} /><pre>{code}</pre></>
  if (!svg) return <Skeleton active paragraph={{ rows: 2 }} title={false} />
  return <div className="mermaid-diagram" role="img" aria-label="文档中的关系图" dangerouslySetInnerHTML={{ __html: svg }} />
}

const schema = {
  ...defaultSchema,
  // The repository owns the Markdown. Keep its stable detail IDs for deep links.
  clobberPrefix: '',
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code ?? []), 'className'],
    details: [...(defaultSchema.attributes?.details ?? []), 'id', 'open'],
  },
}

export default function Markdown({ content, sourcePath = 'RESEARCH.md' }: { content: string; sourcePath?: string }) {
  const location = useLocation()

  useEffect(() => {
    if (!location.hash) return
    let id: string
    try { id = decodeURIComponent(location.hash.slice(1)) } catch { return }
    const target = document.getElementById(id)
    if (!target) return
    const details = target.closest('details')
    if (details) details.open = true
    target.scrollIntoView({ block: 'start' })
  }, [location.hash, location.pathname, content])

  return <div className="markdown-body">
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw, [rehypeSanitize, schema], rehypeSlug]}
      components={{
        a({ href, children }) {
          const target = resolveDocumentLink(href ?? '', sourcePath)
          if (!target) return <span>{children}</span>
          if (target.startsWith('/') && !target.startsWith('//')) return <Link to={target}>{children}</Link>
          if (target.startsWith('#')) return <Link to={`${location.pathname}${target}`}>{children}</Link>
          return <a href={target} target="_blank" rel="noreferrer">{children}</a>
        },
        table({ children }) {
          return <div className="markdown-table-scroll" tabIndex={0} role="region" aria-label="文档表格"><table>{children}</table></div>
        },
        code({ className, children }) {
          const code = String(children).replace(/\n$/, '')
          if (className?.includes('language-mermaid')) return <MermaidDiagram code={code} />
          return <code className={className}>{children}</code>
        },
        pre({ children }) {
          const diagram = Children.toArray(children).some(child => isValidElement<{ className?: string }>(child) && child.props.className?.includes('language-mermaid'))
          return diagram ? <>{children}</> : <pre>{children}</pre>
        },
      }}
    >{content}</ReactMarkdown>
  </div>
}
