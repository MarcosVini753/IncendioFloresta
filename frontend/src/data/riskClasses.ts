import type { RiskClassId } from '../types/susceptibility'

export const RISK_CLASSES: { id: RiskClassId; label: string; lower: number; upper: number; color: string }[] = [
  { id: 'very_low', label: 'Muito baixo', lower: 0, upper: 50, color: '#1a9850' },
  { id: 'low', label: 'Baixo', lower: 50, upper: 70, color: '#91cf60' },
  { id: 'moderate', label: 'Moderado', lower: 70, upper: 90, color: '#fee08b' },
  { id: 'high', label: 'Alto', lower: 90, upper: 95, color: '#fc8d59' },
  { id: 'very_high', label: 'Muito alto', lower: 95, upper: 100, color: '#d73027' },
]
