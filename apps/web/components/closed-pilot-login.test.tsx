import {render,screen,cleanup} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {Login} from './workspace';
afterEach(cleanup);
it('hides signup in a closed pilot while preserving login and recovery',()=>{
  render(<Login accountMode registrationOpen={false} onLogin={vi.fn()}/>);
  expect(screen.getByText('פיילוט פרטי — ההרשמה סגורה')).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'יצירת חשבון חדש'})).not.toBeInTheDocument();
  expect(screen.getByLabelText('שם משתמש')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'שכחתם סיסמה? שחזור באמצעות מפתח'})).toBeInTheDocument();
});
