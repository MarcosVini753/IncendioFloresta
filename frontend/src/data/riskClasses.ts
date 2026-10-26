import type { RiskClassId } from '../types/susceptibility'

export const RISK_CLASSES: { id: RiskClassId; label: string; lower: number; upper: number; color: string }[] = [
  { id: 'very_low', label: 'Muito baixo', lower: 0, upper: 50, color: '#238677' },
  { id: 'low', label: 'Baixo', lower: 50, upper: 70, color: '#8cc89a' },
  { id: 'moderate', label: 'Moderado', lower: 70, upper: 90, color: '#efd47b' },
  { id: 'high', label: 'Alto', lower: 90, upper: 95, color: '#e9a066' },
  { id: 'very_high', label: 'Muito alto', lower: 95, upper: 100, color: '#cb5c52' },
]
