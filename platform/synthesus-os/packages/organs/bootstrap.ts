import { OrganRegistry, OrganType } from './registry';
import { AnomalyEventOrgan } from './shared/AnomalyEventOrgan';
import { ForecastOrgan } from './shared/ForecastOrgan';
import { MemoryOrgan } from './shared/MemoryOrgan';
import { PredictionOrgan } from './shared/PredictionOrgan';
import { RelationOrgan } from './shared/RelationOrgan';
import { SequencePredictionOrgan } from './shared/SequencePredictionOrgan';
import { SummarizerOrgan } from './shared/SummarizerOrgan';

let defaultsRegistered = false;

export function registerDefaultOrgans(): void {
  if (defaultsRegistered) return;

  if (!OrganRegistry.getOrgan(OrganType.Prediction)) {
    OrganRegistry.registerOrgan(new PredictionOrgan());
  }

  if (!OrganRegistry.getOrgan(OrganType.Forecast)) {
    OrganRegistry.registerOrgan(new ForecastOrgan());
  }

  if (!OrganRegistry.getOrgan(OrganType.SequencePrediction)) {
    OrganRegistry.registerOrgan(new SequencePredictionOrgan());
  }

  if (!OrganRegistry.getOrgan(OrganType.Relation)) {
    OrganRegistry.registerOrgan(new RelationOrgan());
  }

  if (!OrganRegistry.getOrgan(OrganType.Memory)) {
    OrganRegistry.registerOrgan(new MemoryOrgan());
  }

  if (!OrganRegistry.getOrgan(OrganType.AnomalyEvent)) {
    OrganRegistry.registerOrgan(new AnomalyEventOrgan());
  }

  if (!OrganRegistry.getOrgan(OrganType.Summarizer)) {
    OrganRegistry.registerOrgan(new SummarizerOrgan());
  }

  defaultsRegistered = true;
}
