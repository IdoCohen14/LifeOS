import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { AcademicSnapshot } from './academic-snapshot';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it.each(['he','en'] as const)('describes exam dates rather than open tasks in %s', async language => {
  const exam = {id:'fixture-exam', title:'Exam fixture', due:'2026-11-07', course_id:'course', course_name:'Course fixture', term_name:'Term fixture'};
  const data = {as_of:'2026-11-05T08:00:00Z', timezone:'Asia/Jerusalem', range_start:'2026-11-05', range_end:'2026-11-12',
    grades:[], grades_truncated:false, upcoming_assignments:[], assignments_total:0, assignments_truncated:false,
    known_effort_hours:null, unestimated_assignments:0, upcoming_exams:[exam], exams_total:1, exams_truncated:false};
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true, status:200, json:async()=>data}));
  const onCourse = vi.fn();
  render(<AcademicSnapshot settings={{display_name:'', language, theme:'dark', timezone:'Asia/Jerusalem'}} csrf="fixture" revision={1} t={(he,en)=>language==='he'?he:en} onUnauthorized={vi.fn()} onCourse={onCourse}/>);
  fireEvent.click(screen.getByRole('button', {name:language==='he'?'הצגת נתוני הלימודים':'Show academic snapshot'}));
  expect(await screen.findByText(language==='he'?'1 מבחנים בטווח':'1 exams in this period', {exact:false})).toBeInTheDocument();
  expect(screen.queryByText(/מבחנים פתוחים|incomplete exams/)).not.toBeInTheDocument();
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name:language==='he'?'פתיחת הקורס':'Open course'}));
  expect(onCourse).toHaveBeenCalledWith('course');
});

it.each(['he','en'] as const)('uses date wording for an empty exam period in %s', async language => {
  const data = {as_of:'2026-11-05T08:00:00Z', timezone:'Asia/Jerusalem', range_start:'2026-11-05', range_end:'2026-11-12',
    grades:[], grades_truncated:false, upcoming_assignments:[], assignments_total:0, assignments_truncated:false,
    known_effort_hours:null, unestimated_assignments:0, upcoming_exams:[], exams_total:0, exams_truncated:false};
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true, status:200, json:async()=>data}));
  render(<AcademicSnapshot settings={{display_name:'', language, theme:'dark', timezone:'Asia/Jerusalem'}} csrf="fixture" revision={1} t={(he,en)=>language==='he'?he:en} onUnauthorized={vi.fn()} onCourse={vi.fn()}/>);
  fireEvent.click(screen.getByRole('button', {name:language==='he'?'הצגת נתוני הלימודים':'Show academic snapshot'}));
  expect(await screen.findByText(language==='he'?'אין מבחנים בטווח הזה. אירועי Moodle מופיעים ביומן.':'No exams in this period. Moodle events appear in the calendar.')).toBeInTheDocument();
});
