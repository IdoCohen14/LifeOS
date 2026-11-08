import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {CachedMailSearch} from './cached-mail-search';
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
it('searches cached sender subject and snippet and navigates without writes',async()=>{
 const fetch=vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>[
 {id:'one',cached_thread_count:2,subject:'Algebra deadline',sender:'Professor fixture',snippet:'Tomorrow assignment',source_url:'https://mail.google.com/mail/u/0/#inbox/one'},
 {id:'two',subject:'Physics deadline',sender:'Professor fixture',snippet:'Tomorrow exam',source_url:'https://mail.google.com/mail/u/0/#inbox/two'},
 {id:'three',subject:'Work',sender:'Recruiter fixture',snippet:'Interview invitation',source_url:'https://mail.google.com/mail/u/0/#inbox/three'}]});vi.stubGlobal('fetch',fetch);
 render(<CachedMailSearch t={(_he,en)=>en} onUnauthorized={vi.fn()}/>);expect(fetch).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Search synchronized mail'}));await screen.findByLabelText('Search subject, sender or text');fireEvent.change(screen.getByLabelText('Search subject, sender or text'),{target:{value:'professor tomorrow'}});expect(screen.getByRole('heading',{name:'Algebra deadline'})).toBeInTheDocument();expect(screen.getByText('This conversation has 2 relevant messages in the current snapshot, including read or reviewed messages.')).toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'Next result'}));expect(screen.getByRole('heading',{name:'Physics deadline'})).toBeInTheDocument();expect(screen.getByRole('link',{name:'Open in Gmail'})).toHaveAttribute('href','https://mail.google.com/mail/u/0/#inbox/two');fireEvent.change(screen.getByLabelText('Search subject, sender or text'),{target:{value:'missing fixture'}});expect(screen.getByText('No matches in synchronized relevant mail.')).toBeInTheDocument();expect(fetch).toHaveBeenCalledTimes(1);expect(fetch.mock.calls[0][0]).toBe('/api/integrations/gmail/messages');expect(fetch.mock.calls[0][1].method).toBe('GET');
});
