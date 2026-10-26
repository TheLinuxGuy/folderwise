import fs from 'node:fs';
import moment from 'moment';
import { Task } from '../src/Task/Task';
import { Status } from '../src/Statuses/Status';
import { StatusRegistry } from '../src/Statuses/StatusRegistry';
import { resetSettings, updateSettings } from '../src/Config/Settings';
import { fromLine } from './TestingTools/TestHelpers';
window.moment = moment;

it('exports Folderwise compatibility fixtures through the Tasks runtime', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-26T12:00:00Z'));
    const source = ' ([source](../alpha/docs/mobile.md "fw:0123456789abcdef"))';
    const rows: any[] = [];
    for (const format of ['tasksPluginEmoji', 'dataview'] as const) {
        for (const [name, suffix, operation] of [
            ['complete', '📅 2026-11-01 ⏫', 'toggle'],
            ['cancel', '📅 2026-11-01', 'cancel'],
            ['reopen', '✅ 2026-10-25', 'toggle'],
            ['daily', '🔁 every day 📅 2026-11-01 🆔 original', 'toggle'],
            ['weekly', '🔁 every week on Monday 📅 2026-11-02', 'toggle'],
            ['monthly', '🔁 every month 📅 2026-11-01', 'toggle'],
            ['when_done', '🔁 every week when done 📅 2026-11-01', 'toggle'],
            ['no_date', '🔁 every day', 'toggle'],
            ['delete', '🏁 delete', 'toggle'],
            ['recur_delete', '🔁 every day 📅 2026-11-01 🏁 delete', 'toggle'],
            ['completed_first', '🔁 every day 📅 2026-11-01', 'toggle'],
        ]) {
            resetSettings(); StatusRegistry.getInstance().resetToDefaultStatuses();
            updateSettings({ setDoneDate: true, setCancelledDate: true, taskFormat: 'tasksPluginEmoji' });
            let task = fromLine({ line: `- [${name === 'reopen' ? 'x' : ' '}] Fixture${source} ${suffix}` });
            expect(task).toBeTruthy();
            if (suffix.includes('📅')) expect(task.dueDate).not.toBeNull();
            if (suffix.includes('🔁')) expect(task.recurrence, name).not.toBeNull();
            updateSettings({ taskFormat: format, recurrenceOnNextLine: name === 'completed_first' });
            const before = task.toFileLineString();
            task = fromLine({ line: before });
            const output = operation === 'cancel'
                ? task.handleNewStatusWithRecurrenceInUsersOrder(Status.CANCELLED)
                : task.toggleWithRecurrenceInUsersOrder();
            const after = output.map(t => t.toFileLineString());
            const normalize = (line: string) => line.replace(source, ' __SOURCE__');
            rows.push({ name: `${format}_${name}`, format, before: normalize(before), after: after.map(normalize) });
        }
    }
    fs.writeFileSync(process.env.FOLDERWISE_TASK_FIXTURES ?? '/tmp/folderwise-tasks-runtime-fixtures.json', JSON.stringify({
        upstream: 'obsidian-tasks-group/obsidian-tasks', commit: '6c7e9a1443e645f29998619974329b61cd2d52dd', version: '8.6.0',
        generatedAt: '2026-10-26T12:00:00Z', cases: rows
    }, null, 2) + '\n');
    vi.useRealTimers();
});
