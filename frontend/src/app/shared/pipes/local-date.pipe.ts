import { Pipe, PipeTransform } from '@angular/core';
import { DatePipe } from '@angular/common';

/**
 * Treats backend datetime strings as UTC (appending 'Z' if absent) and
 * renders them in the user's local timezone using Angular's DatePipe.
 */
@Pipe({ name: 'localDate', standalone: true })
export class LocalDatePipe implements PipeTransform {
  private datePipe = new DatePipe('en-US');

  transform(value: string | null | undefined, format = 'MMM d, h:mm a'): string | null {
    if (!value) return null;
    const utc = value.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(value) ? value : value + 'Z';
    return this.datePipe.transform(utc, format);
  }
}
