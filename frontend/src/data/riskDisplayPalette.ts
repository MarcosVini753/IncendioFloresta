import { RISK_V6_CLASSES } from '../types/riskV6'

// Paleta exclusiva do frontend: não altera os limites, dados ou o contrato v6.
const DISPLAY_COLORS = [
  '#238677',
  '#8cc89a',
  '#efd47b',
  '#e9a066',
  '#cb5c52',
] as const

export const RISK_DISPLAY_CLASSES = RISK_V6_CLASSES.map((item, index) => ({
  ...item,
  color: DISPLAY_COLORS[index],
}))
