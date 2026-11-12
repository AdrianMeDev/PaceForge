import { AbstractControl, ValidationErrors } from '@angular/forms';

/** Group validator for forms with `password` and `passwordConfirm`. */
export function passwordsMatch(group: AbstractControl): ValidationErrors | null {
  return group.get('password')?.value === group.get('passwordConfirm')?.value
    ? null
    : { passwordMismatch: true };
}
