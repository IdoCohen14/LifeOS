import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { BraudeRosterPreview, type RosterPreview } from './braude-roster-preview';

const t = (_he: string, en: string) => en;
const settings = {language:'en' as const, timezone:'Asia/Jerusalem'};
afterEach(cleanup);
const preview: RosterPreview = {fixture:true, status:'ready', reason:null, observed_at:'2026-11-05T08:00:00Z',
  counts:{unchanged:1, added:1, changed:1, missing:1}, rows:[
    {kind:'added', code:'11111', name:'Fixture new', local_name:null, source_name:'Fixture new', local_instructor:null, source_instructor:'Fixture lecturer', fields:[], missing_fields:[]},
    {kind:'changed', code:'22222', name:'Fixture source', local_name:'Local edit', source_name:'Fixture source', local_instructor:'Local lecturer', source_instructor:'Other lecturer', fields:['name','instructor'], missing_fields:[]},
    {kind:'missing', code:'33333', name:'Fixture retained', local_name:'Fixture retained', source_name:null, local_instructor:'Lecturer', source_instructor:null, fields:[], missing_fields:[]},
    {kind:'unchanged', code:'44444', name:'Unchanged fixture', local_name:'Unchanged fixture', source_name:'Unchanged fixture', local_instructor:'Lecturer', source_instructor:'Lecturer', fields:[], missing_fields:[]},
  ]};

describe('read-only fixture roster preview', () => {
  it('shows a compact fixture summary with details closed and no apply action', () => {
    const {container} = render(<BraudeRosterPreview preview={preview} settings={settings} t={t}/>);
    expect(screen.getByText('Fixture only · not connected to the college')).toBeInTheDocument();
    expect(screen.getByText('3 differences · 1 unchanged')).toBeInTheDocument();
    const details = container.querySelector('details')!;
    expect(details.open).toBe(false);
    fireEvent.click(screen.getByText('Review differences'));
    expect(details.open).toBe(true);
    expect(screen.getByText('Not in this report · course retained')).toBeInTheDocument();
    expect(screen.getByText('Local edit')).toBeInTheDocument();
    expect(screen.getByText('Other lecturer')).toBeInTheDocument();
    expect(screen.queryByText('Unchanged fixture')).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('does not claim an incomplete source is current', () => {
    render(<BraudeRosterPreview preview={{...preview, status:'needs_review', reason:'incomplete_source', rows:[]}} settings={settings} t={t}/>);
    expect(screen.getByRole('status')).toHaveTextContent('The report is incomplete. Existing courses are retained.');
    expect(screen.queryByText('Review differences')).not.toBeInTheDocument();
  });

  it('shows login-required without credentials or a login action', () => {
    render(<BraudeRosterPreview preview={{fixture:true, status:'login_required', reason:'login_required'}} settings={settings} t={t}/>);
    expect(screen.getByRole('status')).toHaveTextContent('Sign-in required. Existing information is retained.');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('keeps unknown source fields explicit and supports Hebrew RTL', () => {
    const row = {...preview.rows![3], missing_fields:['instructor' as const], source_instructor:null};
    const {container} = render(<BraudeRosterPreview preview={{...preview, counts:{unchanged:1, added:0, changed:0, missing:0}, rows:[row]}} settings={{...settings, language:'he'}} t={(he)=>he}/>);
    expect(container.querySelector('section')).toHaveAttribute('dir','rtl');
    expect(screen.getByText('מרצה לא סופק במקור')).toBeInTheDocument();
    expect(screen.getByText('זו בדיקת הבדלים בלבד; לא שונה מידע.')).toBeInTheDocument();
  });

  it('refuses reports without the fixture marker', () => {
    const {container} = render(<BraudeRosterPreview preview={{...preview, fixture:false} as unknown as RosterPreview} settings={settings} t={t}/>);
    expect(container).toBeEmptyDOMElement();
  });
});
