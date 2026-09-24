import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { TimeSlider } from './TimeSlider'

const dates = Array.from({ length: 365 }, (_, offset) =>
  new Date(Date.UTC(2015, 0, offset + 1)).toISOString().slice(0, 10),
)

describe('navegação anual do perigo', () => {
  it('apresenta 365 posições e bloqueia o botão anterior no primeiro dia', () => {
    const html = renderToStaticMarkup(createElement(TimeSlider, {
      dates, selectedDate: '2015-01-01', onChange: () => {},
    }))
    expect(html).toContain('01/01/2015')
    expect(html).toContain('31/12/2015')
    expect(html).toMatch(/<button(?=[^>]*aria-label="Dia anterior")(?=[^>]*disabled)[^>]*>/)
    expect(html).toMatch(/max="364"/)
    expect(html).toMatch(/value="0"/)
  })

  it('bloqueia o botão seguinte no último dia', () => {
    const html = renderToStaticMarkup(createElement(TimeSlider, {
      dates, selectedDate: '2015-12-31', onChange: () => {},
    }))
    expect(html).toMatch(/<button(?=[^>]*aria-label="Próximo dia")(?=[^>]*disabled)[^>]*>/)
    expect(html).toMatch(/value="364"/)
  })
})
