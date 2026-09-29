import React, { useState } from 'react';
import { Camera, Save, KeyRound } from 'lucide-react';
import { accountApi } from '../api';
import { normalizeUser, type AuthUser } from '../lib/permissions';
import { PageHeading } from './ManagementUI';

async function avatarFromFile(file:File):Promise<string> {
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>5*1024*1024) throw new Error('请选择不超过 5 MB 的 PNG、JPG 或 WebP 图片');
  const url=URL.createObjectURL(file);
  try {
    const image=new Image();image.src=url;await image.decode();
    const canvas=document.createElement('canvas');canvas.width=128;canvas.height=128;
    const ctx=canvas.getContext('2d');if(!ctx)throw new Error('浏览器无法处理图片');
    const side=Math.min(image.naturalWidth,image.naturalHeight);
    ctx.drawImage(image,(image.naturalWidth-side)/2,(image.naturalHeight-side)/2,side,side,0,0,128,128);
    return canvas.toDataURL('image/png');
  } finally {URL.revokeObjectURL(url);}
}

export default function ProfileScreen({ user, onChanged, onProfileChanged }: { user: AuthUser; onChanged: () => void; onProfileChanged:(user:AuthUser)=>void }) {
  const [form,setForm]=useState({old:'',password:'',confirm:''});
  const [name,setName]=useState(user.displayName);const [avatar,setAvatar]=useState(user.avatarData||null);
  const [message,setMessage]=useState('');const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  return <div className="erp-ui space-y-6">
    <PageHeading title={user.mustChangePassword?'首次登录，请修改临时密码':'个人账号'} description={`${user.username} · ${user.roleLabel}`}/>
    {!user.mustChangePassword&&<section className="ui-card max-w-3xl"><div className="border-b border-slate-200 px-6 py-4"><h2 className="text-sm font-semibold">个人资料</h2></div><form className="space-y-5 p-6" onSubmit={async e=>{e.preventDefault();setMessage('');setError('');setBusy(true);try{const result=await accountApi.saveProfile(name,avatar);onProfileChanged(normalizeUser(result.user));setMessage('个人资料已保存');}catch(e){setError(e instanceof Error?e.message:'保存失败');}finally{setBusy(false);}}}>
      <div className="flex items-center gap-5"><div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-full bg-blue-50 text-2xl font-semibold text-blue-600">{avatar?<img src={avatar} alt="头像预览" className="h-full w-full object-cover"/>:name.charAt(0)}</div><div className="space-y-2"><label className="ui-button cursor-pointer"><Camera className="h-4 w-4"/>更换头像<input aria-label="上传头像" type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" disabled={busy} onChange={async e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;setBusy(true);setError('');try{setAvatar(await avatarFromFile(file));}catch(e){setError(e instanceof Error?e.message:'图片读取失败');}finally{setBusy(false);}}}/></label>{avatar&&<button type="button" className="ml-2 text-xs text-slate-500 hover:text-red-600" onClick={()=>setAvatar(null)}>移除头像</button>}<p className="text-xs text-slate-400">PNG、JPG、WebP，最大 5 MB；自动裁剪为正方形。</p></div></div>
      <label className="block max-w-md text-xs font-medium text-slate-500">显示名称<input className="mt-2 block w-full" required maxLength={64} value={name} onChange={e=>setName(e.target.value)}/></label><button disabled={busy} className="ui-primary"><Save className="h-4 w-4"/>保存资料</button>
    </form></section>}
    {message&&<p role="status" className="text-sm text-emerald-700">{message}</p>}{error&&<p role="alert" className="text-sm text-red-600">{error}</p>}
    <section className="ui-card max-w-3xl"><div className="border-b border-slate-200 px-6 py-4"><h2 className="text-sm font-semibold">修改密码</h2><p className="mt-1 text-xs text-slate-500">密码为 12–128 个字符。修改成功后，所有原登录会话失效，请重新登录。</p></div>
    <form className="space-y-4 p-6" onSubmit={async event=>{event.preventDefault();setError('');setMessage('');if(form.password!==form.confirm){setError('两次新密码不一致');return;}setBusy(true);try{await accountApi.changePassword(form.old,form.password,form.confirm);onChanged();}catch(e){setError(e instanceof Error?e.message:'修改失败');}finally{setBusy(false);}}}>
      {([['old','当前密码'],['password','新密码'],['confirm','确认新密码']] as const).map(([key,label])=><label key={key} className="block max-w-md text-xs font-medium text-slate-500">{label}<input className="mt-2 block w-full" type="password" autoComplete={key==='old'?'current-password':'new-password'} required minLength={key==='old'?1:12} maxLength={128} value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value})}/></label>)}
      <button disabled={busy} className="ui-primary"><KeyRound className="h-4 w-4"/>{busy?'保存中…':'修改密码并重新登录'}</button>
    </form></section>
  </div>;
}
