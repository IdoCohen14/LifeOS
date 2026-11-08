import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AcademicStartGuide } from "./academic-start-guide";
afterEach(cleanup);
it("guides empty setup through explicit dependency-gated actions without creating data",()=>{
 const term=vi.fn(),course=vi.fn(),item=vi.fn(),session=vi.fn();
 const props={hasTerm:false,hasCourse:false,hasItem:false,t:(_he:string,en:string)=>en,onTerm:term,onCourse:course,onItem:item,onSession:session};
 const view=render(<AcademicStartGuide {...props}/>);
 expect(screen.getByRole("progressbar",{name:"Academic setup progress"})).toHaveAttribute("value","0");
 expect(screen.getByRole("button",{name:"Add a course"})).toBeDisabled();
 expect(screen.getByRole("button",{name:"Add your first assignment"})).toBeDisabled();
 expect(term).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button",{name:"Add a term"}));expect(term).toHaveBeenCalledOnce();
 view.rerender(<AcademicStartGuide {...props} hasTerm/>);
 fireEvent.click(screen.getByRole("button",{name:"Add a course"}));expect(course).toHaveBeenCalledOnce();
 view.rerender(<AcademicStartGuide {...props} hasTerm hasCourse/>);
 fireEvent.click(screen.getByRole("button",{name:"Add your first assignment"}));expect(item).toHaveBeenCalledOnce();
 fireEvent.click(screen.getByRole("button",{name:"Add an optional weekly session"}));expect(session).toHaveBeenCalledOnce();
 expect(screen.getByRole("progressbar",{name:"Academic setup progress"})).toHaveAttribute("value","2");
});
it("collapses configured steps without requiring a timetable or claiming academic completion",()=>{
 render(<AcademicStartGuide hasTerm hasCourse hasItem t={(_he,en)=>en} onTerm={vi.fn()} onCourse={vi.fn()} onItem={vi.fn()} onSession={vi.fn()}/>);
 const summary=screen.getByText("Start managing your studies",{exact:true});
 expect(summary.closest("details")).not.toHaveAttribute("open");
 fireEvent.click(summary);
 expect(screen.getByRole("progressbar",{name:"Academic setup progress"})).toHaveAttribute("value","3");
 expect(screen.getByText("A weekly timetable is optional. Add it when you have fixed class times.",{exact:true})).toBeVisible();
});
