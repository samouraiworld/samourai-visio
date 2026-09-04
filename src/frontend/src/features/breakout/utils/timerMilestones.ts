export const findCrossedTimerMilestone = (
  previous: number,
  remaining: number
): number | undefined =>
  [300, 60, 30, 10, 0]
    .filter((milestone) => previous > milestone && remaining <= milestone)
    .at(-1)
