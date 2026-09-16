// Run with Node and an installed @electric-sql/pglite module (path optional as first argument).
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const { PGlite } = await import(process.argv[2] || '@electric-sql/pglite');
const db = new PGlite();
await db.exec(`
  CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
  CREATE TABLE conversas (
    id uuid PRIMARY KEY, workspace_id uuid, channel text, canal_id text, contact_phone text,
    created_at timestamptz, last_message_at timestamptz, last_message text,
    assigned_to text, status text, unread_count integer, bot_activated boolean,
    customer_name text, merged_into uuid
  );
  CREATE TABLE conversation_reconciliation_audit (
    id bigint GENERATED ALWAYS AS IDENTITY,workspace_id uuid,entity_type text,
    entity_id uuid,original_row jsonb,created_at timestamptz DEFAULT now()
  );
  CREATE TABLE agent_configuration_catalog(key text PRIMARY KEY,definition jsonb);
  ALTER TABLE conversas ENABLE ROW LEVEL SECURITY;
`);
await db.exec(await readFile(new URL('../supabase/migrations/20260915180040_contact_conversation_inbox.sql', import.meta.url), 'utf8'));
const consentMigration = await readFile(new URL('../supabase/migrations/20260916035808_confirmed_human_handoff.sql', import.meta.url), 'utf8');
await db.exec(consentMigration);
const id = (n) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`;
const ws = id(900);
async function insert(n, values = {}) {
  const row = { id: id(n), workspace_id: ws, channel: 'whatsapp', canal_id: null, contact_phone: '558599948149',
    created_at: `2026-09-01T00:${String(n % 60).padStart(2, '0')}:00Z`, last_message_at: `2026-09-15T12:${String(n % 60).padStart(2, '0')}:00Z`,
    last_message: `Mensagem ${n}`, assigned_to: null, status: 'active', unread_count: 1, bot_activated: true, customer_name: 'Mesmo nome', ...values };
  await db.query(`INSERT INTO conversas (${Object.keys(row).join(',')}) VALUES (${Object.keys(row).map((_, i) => '$' + (i + 1)).join(',')})`, Object.values(row));
}
await insert(1, { status: 'closed' });
await insert(2, { status: 'waiting', handoff_requested_at: '2026-09-15T12:02:00Z', handoff_reason: 'customer_requested_human', contact_phone: '+55 (85) 9994-8149' });
await insert(3);
await insert(4, { workspace_id: id(901) });
await insert(5, { channel: 'instagram' });
await insert(6, { canal_id: 'other-account' });
await insert(7, { contact_phone: null });
await insert(8, { contact_phone: null });
await insert(9, { workspace_id: null });
await insert(10, { merged_into: id(1) });
const contacts = () => db.query('SELECT * FROM conversation_contact_inbox WHERE workspace_id=$1 ORDER BY last_message_at DESC LIMIT 60', [ws]);
let groups = (await contacts()).rows;
assert.equal(groups.length, 5, 'same names, other channels/connections and missing identities stay separate');
let group = groups.find((g) => g.id === id(1));
assert.deepEqual(group.session_ids, [id(1), id(2), id(3)]);
assert.equal(group.active_session_id, id(3), 'outbound uses newest open session, even when an older one requested a human');
assert.equal(group.current_session.status, 'waiting', 'older waiting session is still represented in the queue');
assert.equal(group.last_message, 'Mensagem 3', 'latest preview independent of actionable session');
assert.equal(group.unread_count, 2, 'closed sessions do not inflate unread queue');
await db.query("UPDATE conversas SET status='active',assigned_to='operator',bot_activated=false WHERE workspace_id=$1 AND id=ANY($2::uuid[]) AND status<>'closed'", [ws, group.session_ids]);
group = (await contacts()).rows.find((g) => g.id === id(1));
assert.equal(group.id, id(1), 'contact id stays stable when claiming');
assert.equal(group.current_session.assigned_to, 'operator');
assert.equal(group.current_session.status, 'active');
assert.equal(group.active_session_id, id(3), 'latest open session routes outbound traffic');
await insert(80, { assigned_to: 'another', last_message_at: '2026-09-15T15:00:00Z' });
group = (await contacts()).rows.find((g) => g.id === id(1));
assert.equal(group.current_session.assigned_to, null, 'mixed ownership does not grant reply access to an unrelated session');
await db.query('DELETE FROM conversas WHERE id=$1', [id(80)]);
await db.query("UPDATE conversas SET status='closed' WHERE workspace_id=$1 AND id=ANY($2::uuid[]) AND status<>'closed'", [ws, group.session_ids]);
group = (await contacts()).rows.find((g) => g.id === id(1));
assert.equal(group.current_session.status, 'closed');
assert.deepEqual(group.session_ids, [id(1), id(2), id(3)], 'closing preserves every historical session');
for (let n = 11; n < 80; n++) await insert(n);
group = (await contacts()).rows.find((g) => g.session_ids.includes(id(1)));
assert.equal(group.session_ids.length, 72, 'grouping happens before inbox limit');
assert.equal((await db.query('SELECT count(*) AS n FROM conversas')).rows[0].n, 79, 'no source rows deleted');
const permission = await db.query("SELECT has_table_privilege('anon','conversation_contact_inbox','SELECT') AS anon, has_table_privilege('authenticated','conversation_contact_inbox','SELECT') AS authenticated, reloptions FROM pg_class WHERE relname='conversation_contact_inbox'");
assert.equal(permission.rows[0].anon, false);
assert.equal(permission.rows[0].authenticated, false);
assert.ok(permission.rows[0].reloptions.includes('security_invoker=true'));
await insert(100, {contact_phone:'5511111111111',status:'waiting'});
let ordinary = (await db.query('SELECT current_session FROM conversation_contact_inbox WHERE id=$1',[id(100)])).rows[0];
assert.equal(ordinary.current_session.status,'active','waiting status alone does not signal a human transfer');
await db.query("INSERT INTO conversation_reconciliation_audit(workspace_id,entity_type,entity_id,original_row) VALUES ($1,'conversation',$2,$3)", [ws,id(100),JSON.stringify({_handoff:{reason:'integration_failure'}})]);
await db.exec(consentMigration);
assert.equal((await db.query('SELECT handoff_requested_at FROM conversas WHERE id=$1',[id(100)])).rows[0].handoff_requested_at,null,'automatic failures are not backfilled as customer consent');
await db.query("INSERT INTO conversation_reconciliation_audit(workspace_id,entity_type,entity_id,original_row) VALUES ($1,'conversation',$2,$3)", [ws,id(100),JSON.stringify({_handoff:{reason:'customer_accepted_handoff_offer'}})]);
await db.exec(consentMigration);
ordinary = (await db.query('SELECT current_session FROM conversation_contact_inbox WHERE id=$1',[id(100)])).rows[0];
assert.equal(ordinary.current_session.status,'waiting');
assert.equal(ordinary.current_session.handoff_reason,'customer_accepted_handoff_offer');
assert.ok(ordinary.current_session.handoff_requested_at);
await db.query("UPDATE conversas SET status='active',assigned_to='operator' WHERE id=$1",[id(100)]);
assert.equal((await db.query('SELECT current_session FROM conversation_contact_inbox WHERE id=$1',[id(100)])).rows[0].current_session.status,'active');
await db.close();
console.log('PASS: contact identity, scope, history preservation, grouping before pagination, claim/close and view permissions.');
