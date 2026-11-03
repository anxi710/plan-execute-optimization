import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { expect, it } from 'vitest';
import { research } from '../content';
import { Questions } from './ResearchPages';

it('shows the current direction menu and its topic groups instead of only the historical P1', () => {
  const menu = research.details.find((item) => item.id === 'direction-menu')!;
  const ids = [...menu.markdown.matchAll(/^\| (D\d+) \|/gm)].map((match) => match[1]);
  const markup = renderToStaticMarkup(<MemoryRouter><Questions /></MemoryRouter>);

  expect(ids.length).toBeGreaterThan(0);
  for (const id of ids) expect(markup).toContain(id);
  for (const section of research.details.filter((item) => item.id.startsWith('directions-'))) {
    expect(markup).toContain(section.title);
  }
  expect(markup).not.toContain('P1 题卡');
});
