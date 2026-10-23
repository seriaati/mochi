import type { Billing, Payment, Project } from './queries.ts'

/** What a payment is for: the project itself (null) or one of its additions. */
export type Target = number | null

/** The amount expected next: what's left of the deposit, otherwise the rest. */
export function nextAmount(billing: Billing): number {
  return billing.deposit_due || billing.final_due
}

/** The figures for a payment target, named "Project" for the project itself. */
export function targetOf(project: Project, target: Target): Billing & { name: string } {
  const addition = project.additions.find((a) => a.id === target)
  return addition ?? { ...project, name: 'Project' }
}

/** "Project deposit", "Loyalty points final payment", "Giveaway feature payment". */
export function paymentLabel(project: Project, payment: Payment): string {
  const name = targetOf(project, payment.addition_id).name
  const kind = { deposit: 'deposit', final: 'final payment', payment: 'payment' }[payment.kind]
  return `${name} ${kind}`
}
