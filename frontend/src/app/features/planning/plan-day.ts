import { Component, input } from '@angular/core';
import { Icon } from '../../shared/icon';
import { Workout } from '../../core/planning/planning-models';
import {
  EQUIPMENT_LABELS,
  GOAL_LABELS,
  REGION_LABELS,
  SLOT_LABELS,
  SPORT_ICONS,
  SPORT_LABELS,
  exerciseDetail,
  exportText,
  minutesText,
  segmentText,
  stretchingText,
  targetText,
} from './plan-format';

/** One day of the plan with its workouts, numbered as the checks number them. */
export interface PlanDay {
  date: string;
  label: string;
  workouts: { number: number; workout: Workout }[];
}

/** One day of a plan: its heading and the workouts of that day. */
@Component({
  selector: 'app-plan-day',
  imports: [Icon],
  templateUrl: './plan-day.html',
  styleUrl: './plan-day.css',
})
export class PlanDayView {
  readonly day = input.required<PlanDay>();

  protected readonly slot = SLOT_LABELS;
  protected readonly sport = SPORT_LABELS;
  protected readonly icon = SPORT_ICONS;
  protected readonly goal = GOAL_LABELS;
  protected readonly region = REGION_LABELS;
  protected readonly equipment = EQUIPMENT_LABELS;
  protected readonly minutes = minutesText;
  protected readonly target = targetText;
  protected readonly segment = segmentText;
  protected readonly exerciseNumbers = exerciseDetail;
  protected readonly stretching = stretchingText;
  protected readonly sent = exportText;
}
