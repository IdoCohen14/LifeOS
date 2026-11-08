import { expect, it } from "vitest";
import { weightedGrade, sourceReference, type Grade } from "./academic";
const grade = (score: number, weight: number | null): Grade => ({
  id: "x",
  course_id: "c",
  title: "x",
  score,
  maximum: 100,
  weight,
});
it("does not invent a final grade from incomplete weights", () => {
  expect(weightedGrade([])).toBeNull();
  expect(weightedGrade([grade(90, null)])).toBeNull();
  expect(weightedGrade([grade(90, 40)])).toBeNull();
  expect(weightedGrade([grade(80, 40), grade(100, 60)])).toBe(92);
});
it("localizes known source references without inventing page numbers", () => {
  expect(sourceReference("slide:2", true)).toBe("שקופית 2");
  expect(sourceReference("document", false)).toBe("Document");
});
