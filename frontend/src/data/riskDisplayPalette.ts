import { RISK_V4_CLASSES } from '../types/riskV4'

// Paleta exclusiva do frontend: não altera os limites, dados ou o contrato v4.
const DISPLAY_COLORS = [
  '#238677',
  '#8cc89a',
  '#efd47b',
  '#e9a066',
  '#cb5c52',
] as const

export const RISK_DISPLAY_CLASSES = RISK_V4_CLASSES.map((item, index) => ({
  ...item,
  color: DISPLAY_COLORS[index],
}))
