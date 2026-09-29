import assert from 'node:assert/strict';
import test from 'node:test';
import { canOpenPage, firstAllowedPage, normalizeUser } from '../src/lib/permissions';

test('purchase disabled permits ledger summaries but not the purchase page',()=>{
  const user=normalizeUser({id:1,username:'reader',display_name:'读者',role_code:'department_user',account_type:'department_user',permissions:['ledger_view'],scope_mode:'selected',department_ids:[1]});
  assert.equal(canOpenPage(user,'ledger'),true);
  assert.equal(canOpenPage(user,'purchases'),false);
  assert.equal(canOpenPage(user,'accounts'),false);
  assert.equal(firstAllowedPage(user),'ledger');
});
test('temporary sessions only open password screen even for super admins',()=>{
  const user=normalizeUser({id:1,username:'admin',display_name:'管理员',role_code:'super_admin',account_type:'super_admin',permissions:[],must_change_password:true});
  assert.equal(canOpenPage(user,'dashboard'),false);
  assert.equal(firstAllowedPage(user),'profile');
});
test('system pages are independently authorized',()=>{
  const user=normalizeUser({id:2,username:'audit',display_name:'审计',role_code:'ledger_admin',permissions:['logs_view']});
  assert.equal(canOpenPage(user,'logs'),true);
  for(const page of ['accounts','backups','maintenance','dashboard','purchases']) assert.equal(canOpenPage(user,page),false);
  assert.equal(firstAllowedPage(user),'logs');
});
