import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { expect, it } from 'vitest';
import { questions, historicalResearch } from '../content';
import { Questions } from './ResearchPages';

it('labels the preserved topic groups as historical', () => {
  const markup = renderToStaticMarkup(<MemoryRouter><Questions /></MemoryRouter>);

  for (const question of questions) expect(markup).toContain(`/questions/${question.id}`);
  for (const section of historicalResearch.details.filter((item) => item.id.startsWith('directions-') && !['directions-current', 'directions-foundation'].includes(item.id))) {
    expect(markup).toContain(section.title);
  }
  expect(markup).not.toContain('P1 题卡');
  expect(markup).toContain('历史问题');
  expect(markup).toContain('/documents/PROPOSAL');
  expect(markup).toContain('/documents/archive%2Fpre-v04%2FRESEARCH#direction-menu');
  expect(markup).toContain('必须取得的判别证据');
  expect(markup).toContain('其他分组与历史');
});
