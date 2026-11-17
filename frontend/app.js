const $ = (s) => document.querySelector(s);
const API = (window.NATQAI_API_BASE || '').replace(/\/$/, '');
const i18n = window.NatqI18n;
const t = (key) => i18n.t(key);
let token = localStorage.getItem('natqai_token') || '';
let currentChat = null;
let authMode = 'login';
let busy = false;
let currentProject = null;

function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2600)}
async function request(path, options={}){
  const headers={'Content-Type':'application/json','Accept-Language':i18n.code,...(options.headers||{})};
  if(token) headers.Authorization=`Bearer ${token}`;
  const response=await fetch(API+path,{...options,headers});
  if(response.status===204)return null;
  const data=await response.json().catch(()=>({detail:t('genericError')}));
  if(!response.ok){if(response.status===401){logout(false)}throw new Error(localizeError(data.detail)||t('requestError'));}
  return data;
}
function localizeError(detail){const map={'مطلوب تسجيل الدخول':t('requestError'),'رمز الدخول غير صالح أو منتهي':t('requestError'),'المستخدم غير موجود':t('requestError'),'البريد الإلكتروني مستخدم مسبقاً':t('requestError'),'بيانات الدخول غير صحيحة':t('requestError'),'المحادثة غير موجودة':t('requestError'),'المشروع غير موجود':t('requestError')};return map[detail]||detail}

async function loadProjects(){
  const projects=await request('/api/v1/projects');
  const list=$('#projectList'); list.replaceChildren();
  if(!projects.length){const empty=document.createElement('p');empty.className='empty-side';empty.textContent=i18n.rtl?'لا توجد مشاريع بعد':'No projects yet';list.appendChild(empty);return;}
  projects.forEach(project=>{const item=document.createElement('button');item.type='button';item.className='chat-item project-item'+(project.id===currentProject?' active':'');item.textContent='▣ '+project.name;item.addEventListener('click',()=>openProject(project));list.appendChild(item);});
}
async function createProject(){
  const name=window.prompt(i18n.rtl?'ما اسم المشروع؟':'Project name?');
  if(!name||!name.trim())return;
  const description=window.prompt(i18n.rtl?'صف المشروع باختصار (اختياري)':'Brief description (optional)')||'';
  try{const project=await request('/api/v1/projects',{method:'POST',body:JSON.stringify({name:name.trim(),description})});await loadProjects();await openProject(project);}
  catch(err){toast(err.message);}
}
async function openProject(project){
  currentProject=project.id;$('#workspaceTitle').textContent=project.name;$('#workspaceDescription').textContent=project.description|| (i18n.rtl?'مساحة ملفات المشروع':'Project file workspace');
  $('#conversation').classList.add('hidden');$('#workspaceView').classList.remove('hidden');$('#sidebar').classList.remove('open');
  $('#filePath').value='';$('#fileContent').value='';$('#workspaceStatus').textContent=i18n.rtl?'اختر ملفاً أو أنشئ ملفاً جديداً.':'Choose a file or create a new one.';
  await loadProjectFiles();await loadProjects();
}
async function loadProjectFiles(){
  if(!currentProject)return;
  const files=await request(`/api/v1/projects/${currentProject}/files`);const list=$('#projectFiles');list.replaceChildren();
  if(!files.length){const empty=document.createElement('p');empty.className='empty-side';empty.textContent=i18n.rtl?'لا توجد ملفات بعد':'No files yet';list.appendChild(empty);return;}
  files.forEach(file=>{const button=document.createElement('button');button.type='button';button.className='file-item';button.textContent=file.path;button.addEventListener('click',()=>openProjectFile(file.path));list.appendChild(button);});
}
async function openProjectFile(path){
  try{const file=await request(`/api/v1/projects/${currentProject}/files/${path.split('/').map(encodeURIComponent).join('/')}`);$('#filePath').value=file.path;$('#fileContent').value=file.content;$('#workspaceStatus').textContent=i18n.rtl?'تم فتح الملف':'File opened';}
  catch(err){toast(err.message);}
}
async function generateProjectFiles(){
  if(!currentProject){toast(i18n.rtl?'اختر مشروعاً أولاً':'Choose a project first');return;}
  const prompt=$('#generatePrompt').value.trim();
  if(prompt.length<10){toast(i18n.rtl?'اكتب وصفاً أوضح للمشروع':'Describe the project in more detail');return;}
  const button=$('#generateProject');button.disabled=true;button.textContent=i18n.rtl?'جارٍ إنشاء الملفات...':'Generating files...';
  try{
    const result=await request(`/api/v1/projects/${currentProject}/generate`,{method:'POST',body:JSON.stringify({prompt,preferred_language:i18n.code})});
    $('#workspaceStatus').textContent=result.summary|| (i18n.rtl?'تم إنشاء الملفات':'Files generated');
    toast(i18n.rtl?`تم إنشاء ${result.files.length} ملفاً`:`Created ${result.files.length} files`);
    await loadProjectFiles();
    if(result.files.length)await openProjectFile(result.files[0].path);
  }catch(err){toast(err.message);}
  finally{button.disabled=false;button.textContent='✦ إنشاء ملفات المشروع بالذكاء الاصطناعي';}
}

async function saveProjectFile(){
  if(!currentProject){toast(i18n.rtl?'اختر مشروعاً أولاً':'Choose a project first');return;}
  const path=$('#filePath').value.trim();if(!path){toast(i18n.rtl?'اكتب مسار الملف أولاً':'Enter a file path first');return;}
  try{const encoded=path.split('/').map(encodeURIComponent).join('/');await request(`/api/v1/projects/${currentProject}/files/${encoded}`,{method:'PUT',body:JSON.stringify({content:$('#fileContent').value})});$('#workspaceStatus').textContent=i18n.rtl?'تم حفظ الملف':'File saved';toast(i18n.rtl?'تم حفظ الملف':'File saved');await loadProjectFiles();}
  catch(err){toast(err.message);}
}

function showAuth(){ $('#authView').classList.remove('hidden');$('#appView').classList.add('hidden'); }
function showApp(){ $('#authView').classList.add('hidden');$('#appView').classList.remove('hidden'); }
function setAuthMode(mode){authMode=mode;document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));$('#nameField').classList.toggle('hidden',mode==='login');$('#authSubmit').innerHTML=`<span>${mode==='login'?t('signIn'):t('createAccount')}</span> <span>${i18n.rtl?'←':'→'}</span>`;$('#authError').textContent='';}
function logout(show=true){token='';currentChat=null;localStorage.removeItem('natqai_token');showAuth();if(show)toast(t('loggedOut'));}
function safeText(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function addMessage(role,content){$('#welcome').classList.add('hidden');const node=document.createElement('article');node.className=`message ${role}`;const avatar=role==='user'?(i18n.rtl?'أنت':'You'):'N';node.innerHTML=`<div class="message-avatar">${avatar}</div><div><div class="bubble" dir="auto">${safeText(content)}</div></div>`;$('#messages').appendChild(node);$('#conversation').scrollTop=$('#conversation').scrollHeight;}
function clearMessages(){ $('#messages').replaceChildren();$('#welcome').classList.remove('hidden');}
async function loadChats(){const chats=await request('/api/v1/chats');const list=$('#chatList');list.replaceChildren();$('#clearChats').disabled=!chats.length;if(!chats.length){const empty=document.createElement('p');empty.className='empty-side';empty.textContent=t('noChats');list.appendChild(empty);return;}chats.forEach(chat=>{const item=document.createElement('div');item.className='chat-item'+(chat.id===currentChat?' active':'');const open=document.createElement('button');open.type='button';open.className='chat-open';open.textContent='◷ '+(chat.title||t('newChat'));open.addEventListener('click',()=>openChat(chat.id));const del=document.createElement('button');del.type='button';del.className='chat-delete';del.title=i18n.rtl?'حذف المحادثة':'Delete conversation';del.setAttribute('aria-label',del.title);del.textContent='×';del.addEventListener('click',async event=>{event.stopPropagation();if(!window.confirm(i18n.rtl?'هل تريد حذف هذه المحادثة نهائياً؟':'Delete this conversation permanently?'))return;try{await request(`/api/v1/chats/${chat.id}`,{method:'DELETE'});if(currentChat===chat.id){currentChat=null;clearMessages();const remaining=chats.filter(c=>c.id!==chat.id);if(remaining.length)await openChat(remaining[0].id);}await loadChats();toast(i18n.rtl?'تم حذف المحادثة':'Conversation deleted');}catch(err){toast(err.message);}});item.append(open,del);list.appendChild(item);});}
async function loadProfile(){const user=await request('/api/v1/users/me');$('#userName').textContent=user.name;$('#userEmail').textContent=user.email;$('#userAvatar').textContent=(user.name||'N').trim().charAt(0).toUpperCase();}
async function loadUsage(){try{const u=await request('/api/v1/usage');$('#usageNote').textContent=t('dailyUsage').replace('{used}',u.messages_used).replace('{limit}',u.daily_message_limit).replace('{tokens}',u.tokens_used);}catch(_){$('#usageNote').textContent='';}}
async function createChat(){const chat=await request('/api/v1/chats',{method:'POST',body:JSON.stringify({})});currentChat=chat.id;clearMessages();await loadChats();$('#messageInput').focus();return chat;}
async function openChat(id){currentChat=id;clearMessages();const data=await request(`/api/v1/chats/${id}/messages`);if(data.length){$('#welcome').classList.add('hidden');data.forEach(m=>addMessage(m.role,m.content));}await loadChats();$('#sidebar').classList.remove('open');}

async function handleChatManagementCommand(message){
  const normalized=message.trim().toLowerCase()
    .replace(/[؟?!.,،؛:]+$/g,'')
    .replace(/\s+/g,' ');

  const allCommands=[
    'امسح جميع المحادثات','احذف جميع المحادثات',
    'امسح كل المحادثات','احذف كل المحادثات',
    'امسح كل محادثاتي','احذف كل محادثاتي',
    'delete all conversations','delete all chats',
    'clear all conversations','clear all chats'
  ];

  const currentCommands=[
    'احذف هذه المحادثة','امسح هذه المحادثة',
    'احذف المحادثة الحالية','امسح المحادثة الحالية',
    'delete this conversation','delete current conversation',
    'delete current chat'
  ];

  const deleteAll=allCommands.includes(normalized);
  const deleteCurrent=currentCommands.includes(normalized);

  if(!deleteAll&&!deleteCurrent)return false;

  addMessage('user',message.trim());

  if(deleteCurrent&&!currentChat){
    addMessage('assistant',i18n.rtl?'لا توجد محادثة مفتوحة لحذفها.':'There is no open conversation to delete.');
    return true;
  }

  const question=deleteAll
    ? (i18n.rtl?'هل أنت متأكد من حذف جميع محادثاتك نهائياً؟ لا يمكن التراجع عن ذلك.':'Delete all your conversations permanently? This cannot be undone.')
    : (i18n.rtl?'هل أنت متأكد من حذف المحادثة الحالية نهائياً؟':'Delete the current conversation permanently?');

  if(!window.confirm(question)){
    addMessage('assistant',i18n.rtl?'تم إلغاء الحذف. لم تُحذف أي محادثة.':'Deletion cancelled. No conversations were deleted.');
    return true;
  }

  try{
    if(deleteAll){
      await request('/api/v1/chats',{method:'DELETE'});
      currentChat=null;
      clearMessages();
      await loadChats();
      toast(i18n.rtl?'تم حذف جميع المحادثات بنجاح':'All conversations deleted successfully');
    }else{
      const deletedId=currentChat;
      await request(`/api/v1/chats/${deletedId}`,{method:'DELETE'});
      currentChat=null;
      clearMessages();
      await loadChats();
      const remaining=await request('/api/v1/chats');
      if(remaining.length)await openChat(remaining[0].id);
      toast(i18n.rtl?'تم حذف المحادثة بنجاح':'Conversation deleted successfully');
    }
  }catch(err){
    addMessage('assistant',(i18n.rtl?'تعذر تنفيذ الحذف: ':'Deletion failed: ')+err.message);
  }

  return true;
}


function isAndroidAppRequest(text){
  const value=String(text||'').trim();
  const creation=/(?:أنشئ|انشئ|اصنع|سو[ّي]|ابنِ|ابني|حوّل|حول|أنشأ|انشاء|إنشاء|بناء|اعمل لي|سوي لي|جهز لي|أريد|اريد|أحتاج|احتاج|أرغب|ارغب|أبغى|ابغى)/i;
  const englishCreation=/\b(?:create|build|make|convert|generate|i want|i need|please make)\b/i;
  const app=/(?:تطبيق|برنامج|app|application)/i;
  const ios=/(?:\bios\b|iphone|ipad|آيفون|ايفون|آيباد)/i;
  // Default unspecified app platforms to NatqAI's Android WebView build pipeline.
  return !ios.test(value)&&app.test(value)&&(creation.test(value)||englishCreation.test(value));
}

function addAndroidProjectAction(project, builderReady, builderMessage){
  const article=document.createElement('article');
  article.className='message assistant';

  const avatar=document.createElement('div');
  avatar.className='message-avatar';
  avatar.textContent='N';

  const wrapper=document.createElement('div');
  const bubble=document.createElement('div');
  bubble.className='bubble chat-action';
  bubble.dir='auto';

  const title=document.createElement('strong');
  title.textContent='تم إنشاء ملفات التطبيق وحفظ المشروع.';
  const detail=document.createElement('p');
  detail.textContent=builderReady
    ? 'خدمة بناء Android جاهزة. لن يبدأ البناء إلا بعد تأكيدك.'
    : (builderMessage||'المشروع محفوظ، لكن خدمة بناء APK غير جاهزة حالياً.');

  const actions=document.createElement('div');
  actions.className='chat-action-buttons';
  let buildButton=null;

  const openButton=document.createElement('button');
  openButton.type='button';
  openButton.className='secondary';
  openButton.textContent='فتح ملفات المشروع';
  openButton.addEventListener('click',()=>openProject(project).catch(err=>toast(err.message)));
  actions.appendChild(openButton);

  if(builderReady){
    buildButton=document.createElement('button');
    buildButton.type='button';
    buildButton.className='primary';
    buildButton.textContent='جارٍ تجهيز APK تلقائياً...';
    buildButton.addEventListener('click',()=>buildChatProjectApk(project.id,buildButton,detail));
    actions.appendChild(buildButton);
  }

  bubble.append(title,detail,actions);
  wrapper.appendChild(bubble);
  article.append(avatar,wrapper);
  $('#messages').appendChild(article);
  $('#conversation').scrollTop=$('#conversation').scrollHeight;
  return {detail,buildButton};
}

async function createAndroidProjectFromChat(userPrompt){
  const projectName = userPrompt.trim()
    .replace(/\s+/g,' ')
    .slice(0,80) || 'تطبيق Android';

  const project=await request('/api/v1/projects',{
    method:'POST',
    body:JSON.stringify({
      name:projectName,
      description:userPrompt.trim().slice(0,2000)
    })
  });

  currentProject=project.id;

  const generationPrompt=[
    'أنشئ تطبيق ويب متكاملاً وصغيراً قابلاً للتغليف داخل Android WebView.',
    'يجب إنشاء ملف index.html في جذر المشروع مباشرة.',
    'استخدم HTML وCSS وJavaScript فقط، مع ملفات نسبية محلية.',
    'اجعل الواجهة متجاوبة مع شاشات الهواتف وتدعم اللغة العربية واتجاه RTL عند الحاجة.',
    'لا تستخدم backend محلياً أو أسراراً أو مفاتيح API أو ملفات ثنائية.',
    'أضف README واضحاً. لا تدّعِ تشغيل التطبيق أو اختباره.',
    'طلب المستخدم:',
    userPrompt
  ].join('\n');

  const generated=await request(`/api/v1/projects/${project.id}/generate`,{
    method:'POST',
    body:JSON.stringify({
      prompt:generationPrompt,
      preferred_language:i18n.code,
      chat_id:currentChat,
      chat_message:userPrompt.trim()
    })
  });

  if(!Array.isArray(generated.files)||!generated.files.some(file=>file.path==='index.html')){
    throw new Error('تم إنشاء المشروع، لكن لم يتم إنشاء index.html في جذر المشروع. افتح المشروع وأصلح الملفات قبل البناء.');
  }

  await loadProjects();
  await loadChats();
  await loadUsage();

  let readiness={ready:false,message:'تعذر التحقق من خدمة البناء.'};
  try{
    readiness=await request(`/api/v1/projects/${project.id}/android-builder-status`);
  }catch(err){
    readiness.message=err.message;
  }

  const action=addAndroidProjectAction(project,Boolean(readiness.ready),readiness.message);
  if(readiness.ready&&action.buildButton){
    await buildChatProjectApk(project.id,action.buildButton,action.detail);
  }
}

async function buildChatProjectApk(projectId,button,detail){
  button.disabled=true;
  button.textContent='جارٍ فحص خدمة البناء...';

  try{
    const readiness=await request(`/api/v1/projects/${projectId}/android-builder-status`);
    if(!readiness.ready)throw new Error(readiness.message||'خدمة بناء APK غير جاهزة.');

    button.textContent='جارٍ بناء APK...';
    detail.textContent='بدأ البناء بعد تأكيدك. يرجى الانتظار.';

    const response=await fetch(API+`/api/v1/projects/${projectId}/android-apk`,{
      method:'POST',
      headers:{Authorization:`Bearer ${token}`}
    });

    if(!response.ok){
      const err=await response.json().catch(()=>({detail:t('requestError')}));
      throw new Error(localizeError(err.detail)||t('requestError'));
    }

    const blob=await response.blob();
    if(blob.size<1024||blob.type!=='application/vnd.android.package-archive'){
      throw new Error('لم يُرجع الخادم ملف APK صالحاً.');
    }

    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;
    link.download=`natqai-debug-${projectId}.apk`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),5000);

    detail.textContent='اكتمل البناء وتم التحقق من ملف APK وبدء تنزيله تلقائياً.';
    button.textContent='اكتمل بناء APK';
    button.disabled=true;
    toast('اكتمل بناء APK بنجاح');
  }catch(err){
    detail.textContent='تعذر بناء APK: '+err.message;
    button.textContent='إعادة محاولة بناء APK';
    toast(err.message);
  }finally{
    if(button.textContent!=='اكتمل بناء APK')button.disabled=false;
  }
}

async function sendMessage(text){if(busy||!text.trim())return;busy=true;$('#sendButton').disabled=true;$('#messageInput').value='';$('#messageInput').style.height='auto';try{if(await handleChatManagementCommand(text))return;
if(!currentChat)await createChat();
if(isAndroidAppRequest(text)){
  addMessage('user',text.trim());
  const pending=document.createElement('div');
  pending.className='typing';
  pending.textContent=i18n.rtl?'جارٍ إنشاء التطبيق وبناء APK تلقائياً...':'Creating the app and building its APK automatically...';
  $('#messages').appendChild(pending);
  $('#conversation').scrollTop=$('#conversation').scrollHeight;
  try{
    await createAndroidProjectFromChat(text.trim());
    pending.remove();
  }catch(err){
    pending.remove();
    addMessage('assistant','تعذر إكمال إنشاء التطبيق: '+err.message);
    throw err;
  }
  return;
}
addMessage('user',text.trim());const pending=document.createElement('div');pending.className='typing';pending.textContent=t('thinking');pending.id='typing';$('#messages').appendChild(pending);$('#conversation').scrollTop=$('#conversation').scrollHeight;const response=await fetch(API+`/api/v1/chats/${currentChat}/stream`,{method:'POST',headers:{'Content-Type':'application/json','Accept':'text/event-stream','Accept-Language':i18n.code,Authorization:`Bearer ${token}`},body:JSON.stringify({message:text.trim(),preferred_language:i18n.code})});if(!response.ok){const err=await response.json().catch(()=>({detail:t('requestError')}));throw new Error(localizeError(err.detail)||t('requestError'));}$('#typing')?.remove();const article=document.createElement('article');article.className='message assistant';article.innerHTML=`<div class="message-avatar">N</div><div><div class="bubble" dir="auto"></div></div>`;$('#messages').appendChild(article);const bubble=article.querySelector('.bubble');const reader=response.body.getReader();const decoder=new TextDecoder();let buffer='',streamError='';while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const events=buffer.split('\n\n');buffer=events.pop()||'';for(const event of events){const line=event.split('\n').find(x=>x.startsWith('data:'));if(!line)continue;const payload=JSON.parse(line.slice(5).trim());if(payload.type==='delta'){bubble.textContent+=payload.content;$('#conversation').scrollTop=$('#conversation').scrollHeight;}else if(payload.type==='error'){streamError=payload.message||t('genericError');}}}if(streamError){article.remove();throw new Error(localizeError(streamError)||streamError);}if(!bubble.textContent.trim()){article.remove();throw new Error(t('genericError'));}await loadChats();await loadUsage();}catch(err){$('#typing')?.remove();toast(err.message);if(err.message.includes('غير مضبوط')||err.message.toLowerCase().includes('not configured'))addMessage('assistant',t('aiNotConfigured'));}finally{busy=false;$('#sendButton').disabled=false;$('#messageInput').focus();}}

$('#authForm').addEventListener('submit',async e=>{e.preventDefault();const form=new FormData(e.currentTarget);const payload=Object.fromEntries(form.entries());$('#authError').textContent='';$('#authSubmit').disabled=true;try{const data=await request(`/api/v1/auth/${authMode}`,{method:'POST',body:JSON.stringify(payload)});token=data.access_token;localStorage.setItem('natqai_token',token);await boot();}catch(err){$('#authError').textContent=err.message;}finally{$('#authSubmit').disabled=false;}});
document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>setAuthMode(b.dataset.mode)));
$('#newChat').addEventListener('click',async()=>{try{await createChat();await loadChats();$('#sidebar').classList.remove('open');}catch(e){toast(e.message)}});
$('#clearChats').addEventListener('click',async()=>{if(!window.confirm(i18n.rtl?'هل تريد حذف جميع المحادثات نهائياً؟ لا يمكن التراجع عن ذلك.':'Delete all conversations permanently? This cannot be undone.'))return;try{await request('/api/v1/chats',{method:'DELETE'});currentChat=null;clearMessages();await loadChats();toast(i18n.rtl?'تم مسح جميع المحادثات':'All conversations deleted');}catch(err){toast(err.message);}});
$('#logout').addEventListener('click',()=>logout());
$('#newProject').addEventListener('click',createProject);
$('#closeWorkspace').addEventListener('click',()=>{$('#workspaceView').classList.add('hidden');$('#conversation').classList.remove('hidden');});
$('#newFile').addEventListener('click',()=>{$('#filePath').value='';$('#fileContent').value='';$('#filePath').focus();$('#workspaceStatus').textContent=i18n.rtl?'أدخل اسم الملف ومحتواه':'Enter a file name and its content';});
$('#saveFile').addEventListener('click',saveProjectFile);
$('#generateProject').addEventListener('click',generateProjectFiles);
$('#checkProject').addEventListener('click',async()=>{
  if(!currentProject){toast(i18n.rtl?'اختر مشروعاً أولاً':'Choose a project first');return;}
  const button=$('#checkProject');const report=$('#reviewReport');button.disabled=true;button.textContent=i18n.rtl?'جارٍ اختبار الصياغة...':'Checking syntax...';report.classList.remove('hidden');report.textContent=i18n.rtl?'جارٍ فحص الملفات دون تشغيلها...':'Checking files without executing them...';
  try{
    const result=await request(`/api/v1/projects/${currentProject}/check`,{method:'POST'});
    report.replaceChildren();const heading=document.createElement('h3');heading.textContent=result.summary;report.appendChild(heading);
    const note=document.createElement('p');note.className='muted';note.textContent=i18n.rtl?'هذا فحص صياغة محدود؛ لم يتم تشغيل أي كود.':'Limited syntax check only; no code was executed.';report.appendChild(note);
    result.results.forEach(item=>{const row=document.createElement('p');row.textContent=`${item.status.toUpperCase()} · ${item.path||'—'} · ${item.message}`;report.appendChild(row);});
    toast(i18n.rtl?'اكتمل اختبار الصياغة':'Syntax check complete');
  }catch(err){report.textContent=err.message;toast(err.message);}
  finally{button.disabled=false;button.textContent=i18n.rtl?'اختبار الصياغة الآمن':'Safe syntax check';}
});

async function loadRailwayStatus(){
  const status=$('#railwayStatus');if(!status)return;
  try{const result=await request('/api/v1/integrations/railway');status.textContent=result.connected?`متصل بحساب Railway: ${result.account_name||result.account_id}`:'غير متصل / Not connected';$('#disconnectRailway').hidden=!result.connected;}
  catch(_){status.textContent='تعذر قراءة حالة الاتصال / Could not load connection status';}
}
$('#connectRailway')?.addEventListener('click',async()=>{
  const input=$('#railwayToken');const tokenValue=input.value.trim();if(!tokenValue){toast('أدخل رمز Railway أولاً');return;}
  const button=$('#connectRailway');button.disabled=true;button.textContent='جارٍ التحقق...';
  try{const result=await request('/api/v1/integrations/railway/connect',{method:'POST',body:JSON.stringify({token:tokenValue})});input.value='';toast(result.message||'تم الاتصال');await loadRailwayStatus();}
  catch(err){toast(err.message);}
  finally{button.disabled=false;button.textContent='التحقق والاتصال بـ Railway';}
});
$('#disconnectRailway')?.addEventListener('click',async()=>{
  if(!window.confirm('هل تريد قطع اتصال Railway وحذف الرمز المحفوظ؟'))return;
  try{await request('/api/v1/integrations/railway',{method:'DELETE'});await loadRailwayStatus();toast('تم قطع الاتصال');}
  catch(err){toast(err.message);}
});

async function loadRailwayProjects(){
  const select=$('#railwayProjectSelect');const report=$('#railwayDeployReport');
  try{const projects=await request('/api/v1/integrations/railway/projects');select.replaceChildren(new Option('اختر المشروع',''));projects.forEach(p=>select.add(new Option(p.name,p.id)));$('#railwayEnvironmentSelect').replaceChildren(new Option('اختر البيئة',''));$('#railwayServiceSelect').replaceChildren(new Option('اختر الخدمة',''));report.textContent=`تم تحميل ${projects.length} مشروعاً من Railway.`;}
  catch(err){report.textContent=err.message;toast(err.message);}
}
$('#loadRailwayProjects')?.addEventListener('click',loadRailwayProjects);
$('#railwayProjectSelect')?.addEventListener('change',async()=>{
  const id=$('#railwayProjectSelect').value;const env=$('#railwayEnvironmentSelect');const svc=$('#railwayServiceSelect');env.replaceChildren(new Option('اختر البيئة',''));svc.replaceChildren(new Option('اختر الخدمة',''));if(!id)return;
  try{const project=await request(`/api/v1/integrations/railway/projects/${encodeURIComponent(id)}`);project.environments.forEach(x=>env.add(new Option(x.name,x.id)));project.services.forEach(x=>svc.add(new Option(x.name,x.id)));$('#railwayDeployReport').textContent=`${project.name}: ${project.services.length} خدمة و${project.environments.length} بيئة.`;}
  catch(err){$('#railwayDeployReport').textContent=err.message;toast(err.message);}
});
$('#refreshRailwayStatus')?.addEventListener('click',async()=>{
  const project_id=$('#railwayProjectSelect').value,service_id=$('#railwayServiceSelect').value,environment_id=$('#railwayEnvironmentSelect').value;const report=$('#railwayDeployReport');
  if(!project_id||!service_id||!environment_id){toast('اختر المشروع والخدمة والبيئة أولاً');return;}
  try{const result=await request(`/api/v1/integrations/railway/deployments/latest?project_id=${encodeURIComponent(project_id)}&service_id=${encodeURIComponent(service_id)}&environment_id=${encodeURIComponent(environment_id)}`);
    if(!result.found){report.textContent='لا توجد عملية نشر لهذه الخدمة بعد.';return;}
    const d=result.deployment;report.textContent=`آخر حالة نشر: ${result.status} · ${d.createdAt||''} · ${d.url||d.staticUrl||d.id}`;
    if(result.is_success)toast('اكتمل النشر بنجاح وفق حالة Railway.');else if(['FAILED','CRASHED'].includes(result.status))toast('فشل النشر؛ راجع سجلات Railway.');else toast(`حالة النشر الحالية: ${result.status}`);
  }catch(err){report.textContent=err.message;toast(err.message);}
});
$('#loadRailwayDeployments')?.addEventListener('click',async()=>{
  const project=$('#railwayProjectSelect').value,service=$('#railwayServiceSelect').value,environment=$('#railwayEnvironmentSelect').value;const report=$('#railwayDeployReport');if(!project||!service||!environment){toast('اختر المشروع والخدمة والبيئة أولاً');return;}
  try{const rows=await request(`/api/v1/integrations/railway/deployments?project_id=${encodeURIComponent(project)}&service_id=${encodeURIComponent(service)}&environment_id=${encodeURIComponent(environment)}`);report.replaceChildren();if(!rows.length){report.textContent='لا توجد عمليات نشر مسجلة لهذه الخدمة.';return;}rows.forEach(x=>{const p=document.createElement('p');p.textContent=`${x.status} · ${x.createdAt||''} · ${x.url||x.staticUrl||x.id}`;report.appendChild(p);});}
  catch(err){report.textContent=err.message;toast(err.message);}
});
let latestDeploymentRunId=null;
async function showDeploymentLogs(kind){
  if(!currentProject||!latestDeploymentRunId){toast('ابدأ نشر ZIP من NatqAI أولاً حتى يتوفر رقم الطلب.');return;}
  const panel=$('#deploymentLogs');panel.hidden=false;panel.textContent='جارٍ تحميل السجلات...';
  try{
    const data=await request(`/api/v1/projects/${currentProject}/deployment-source/runs/${latestDeploymentRunId}/logs?kind=${kind}`);
    panel.textContent=(data.lines||[]).join('\n')||'لا توجد سجلات متاحة حالياً.';
    if(data.truncated)panel.textContent+='\n[تم اختصار المخرجات لحماية الواجهة]';
  }catch(err){panel.textContent=err.message||'تعذر تحميل السجلات.';}
}
$('#showBuildLogs')?.addEventListener('click',()=>showDeploymentLogs('build'));
$('#showRuntimeLogs')?.addEventListener('click',()=>showDeploymentLogs('runtime'));

$('#deployUploadedSource')?.addEventListener('click',async()=>{
  const report=$('#railwayDeployReport'),button=$('#deployUploadedSource');
  const railway_project_id=$('#railwayProjectSelect')?.value,railway_service_id=$('#railwayServiceSelect')?.value,railway_environment_id=$('#railwayEnvironmentSelect')?.value;
  if(!currentProject){toast('اختر مشروع NatqAI أولاً.');return;}
  if(!railway_project_id||!railway_service_id||!railway_environment_id){toast('اختر مشروع Railway والخدمة والبيئة.');return;}
  if(!confirm('سيتم رفع آخر ملف ZIP محفوظ إلى Railway وبدء عملية بناء ونشر. هل تريد المتابعة؟'))return;
  button.disabled=true;
  try{
    const result=await request(`/api/v1/projects/${currentProject}/deployment-source/deploy`,{method:'POST',body:JSON.stringify({railway_project_id,railway_service_id,railway_environment_id})});
    report.textContent=`${result.status} · ${result.message} · رقم الطلب: ${result.run_id}`;
    const runId=result.run_id;latestDeploymentRunId=runId;$('#deploymentLogs').hidden=true;$('#deploymentLogs').textContent='';
    let pollCount=0;const poll=async()=>{try{const state=await request(`/api/v1/projects/${currentProject}/deployment-source/runs/${runId}`);const remote=state.remote_status||'';report.replaceChildren();const line=document.createElement('p');line.textContent=`${state.status.toUpperCase()}${remote?' · Railway: '+remote:''} · ${state.message} · رقم الطلب: ${runId}`;report.appendChild(line);if(state.deployment_url){const link=document.createElement('a');link.href=state.deployment_url.startsWith('https://')?state.deployment_url:'#';link.target='_blank';link.rel='noopener noreferrer';link.textContent='فتح الموقع المنشور';if(link.href!=='#')report.appendChild(link);}const terminal=['SUCCESS','FAILED','CRASHED','NEEDS_APPROVAL','SLEEPING','SKIPPED','REMOVED','REMOVING','UNKNOWN'].includes(remote);if(!terminal&&pollCount++<120)setTimeout(poll,10000);else if(remote==='SUCCESS')toast('اكتمل النشر بنجاح وفق حالة Railway.');else if(['FAILED','CRASHED'].includes(remote))toast('فشل النشر؛ راجع سجلات Railway.');}catch(e){report.textContent=e.message||'تعذر تحديث حالة طلب النشر.';}};
    setTimeout(poll,3000);
  }catch(e){report.textContent=e.message||'تعذر بدء رفع المشروع إلى Railway.';}
  finally{button.disabled=false;}
});

async function runRailwayServiceAction(action){
  const project_id=$('#railwayProjectSelect')?.value,service_id=$('#railwayServiceSelect')?.value,environment_id=$('#railwayEnvironmentSelect')?.value;const report=$('#railwayDeployReport');
  if(!project_id||!service_id||!environment_id){toast('اختر مشروع Railway والخدمة والبيئة أولاً');return;}
  const isStop=action==='stop';
  const promptText=isStop?'تنبيه: سيزيل Railway آخر نشر ناجح، وقد يصبح الموقع غير متاح. لن تُحذف الخدمة أو إعداداتها. هل تريد المتابعة؟':'سيطلب Railway إعادة نشر آخر إصدار للمصدر المرتبط. قد تترتب كلفة استضافة. هل تريد المتابعة؟';
  if(!window.confirm(promptText))return;
  const button=$(isStop?'#stopRailwayService':'#redeployRailwayService');button.disabled=true;
  try{const result=await request('/api/v1/integrations/railway/service-action',{method:'POST',body:JSON.stringify({action,project_id,service_id,environment_id,...(isStop?{confirm_stop:true}:{})})});report.textContent=`${result.status} · ${result.message}`;toast(isStop?'تم قبول طلب إيقاف النشر؛ تحقق من الحالة في Railway.':'تم قبول طلب إعادة النشر؛ تحقق من الحالة النهائية.');}
  catch(err){report.textContent=err.message||'تعذر تنفيذ الإجراء.';toast(err.message||'تعذر تنفيذ الإجراء.');}
  finally{button.disabled=false;}
}

function selectedRailwayScope(){
  return {project_id:$('#railwayProjectSelect')?.value,service_id:$('#railwayServiceSelect')?.value,environment_id:$('#railwayEnvironmentSelect')?.value};
}
function requireRailwayScope(scope){
  if(!scope.project_id||!scope.service_id||!scope.environment_id){toast('اختر مشروع Railway والخدمة والبيئة أولاً');return false;}
  return true;
}
$('#loadRailwayDomains')?.addEventListener('click',async()=>{
  const scope=selectedRailwayScope();if(!requireRailwayScope(scope))return;const report=$('#railwayDeployReport');
  try{const result=await request(`/api/v1/integrations/railway/domains?project_id=${encodeURIComponent(scope.project_id)}&service_id=${encodeURIComponent(scope.service_id)}&environment_id=${encodeURIComponent(scope.environment_id)}`);
    const select=$('#railwayDomainSelect');select.replaceChildren(new Option('اختر نطاقاً لفحصه أو حذفه',''));
    const rows=Array.isArray(result.domains)?result.domains:(result.domains?.domains||result.domains?.data||[]);
    rows.forEach(item=>{const domain=typeof item==='string'?item:(item.domain||item.name||item.hostname);if(domain)select.add(new Option(domain,domain));});
    report.textContent=`تم تحميل ${rows.length} نطاقاً من الخدمة المحددة.`;
  }catch(err){report.textContent=err.message;toast(err.message);}
});
$('#addRailwayDomain')?.addEventListener('click',async()=>{
  const scope=selectedRailwayScope();if(!requireRailwayScope(scope))return;
  const domain=$('#railwayCustomDomain').value.trim().toLowerCase();const port=$('#railwayDomainPort').value.trim();
  if(!domain){toast('أدخل اسم النطاق أولاً');return;}
  if(!window.confirm(`سيتم ربط ${domain} بالخدمة المحددة في Railway. قد تحتاج إلى تعديل سجلات DNS. هل تريد المتابعة؟`))return;
  const button=$('#addRailwayDomain');button.disabled=true;
  try{const result=await request('/api/v1/integrations/railway/domains',{method:'POST',body:JSON.stringify({...scope,domain,...(port?{port:Number(port)}:{})})});
    $('#railwayDeployReport').textContent=`${result.status} · ${result.message}\n${JSON.stringify(result.result,null,2)}`;toast('قُبل طلب إضافة النطاق. راجع سجلات DNS المعادة من Railway.');await $('#loadRailwayDomains').click();
  }catch(err){$('#railwayDeployReport').textContent=err.message;toast(err.message);}
  finally{button.disabled=false;}
});
$('#checkRailwayDomain')?.addEventListener('click',async()=>{
  const scope=selectedRailwayScope();if(!requireRailwayScope(scope))return;const domain=$('#railwayDomainSelect').value;if(!domain){toast('اختر نطاقاً أولاً');return;}
  try{const result=await request(`/api/v1/integrations/railway/domains/status?domain=${encodeURIComponent(domain)}&project_id=${encodeURIComponent(scope.project_id)}&service_id=${encodeURIComponent(scope.service_id)}&environment_id=${encodeURIComponent(scope.environment_id)}`);
    $('#railwayDeployReport').textContent=`حالة النطاق ${domain}:\n${JSON.stringify(result.status,null,2)}`;
  }catch(err){$('#railwayDeployReport').textContent=err.message;toast(err.message);}
});
$('#deleteRailwayDomain')?.addEventListener('click',async()=>{
  const scope=selectedRailwayScope();if(!requireRailwayScope(scope))return;const domain=$('#railwayDomainSelect').value;if(!domain){toast('اختر نطاقاً أولاً');return;}
  if(!window.confirm(`تحذير: سيتم حذف ${domain} من الخدمة المحددة وقد يتوقف الموقع عن العمل عبر هذا العنوان. هل أنت متأكد؟`))return;
  try{const result=await request('/api/v1/integrations/railway/domains',{method:'DELETE',body:JSON.stringify({...scope,domain,confirm_delete:true})});$('#railwayDeployReport').textContent=`${result.status} · ${result.message}`;await $('#loadRailwayDomains').click();
  }catch(err){$('#railwayDeployReport').textContent=err.message;toast(err.message);}
});

$('#redeployRailwayService')?.addEventListener('click',()=>runRailwayServiceAction('redeploy'));
$('#stopRailwayService')?.addEventListener('click',()=>runRailwayServiceAction('stop'));

$('#deployRailwayService')?.addEventListener('click',async()=>{
  const project_id=$('#railwayProjectSelect').value,service_id=$('#railwayServiceSelect').value,environment_id=$('#railwayEnvironmentSelect').value;const report=$('#railwayDeployReport');if(!project_id||!service_id||!environment_id){toast('اختر المشروع والخدمة والبيئة أولاً');return;}
  if(!window.confirm('سيتم إرسال طلب نشر للخدمة المحددة على Railway وقد تترتب عليه كلفة استضافة. هل تريد المتابعة؟'))return;
  const button=$('#deployRailwayService');button.disabled=true;try{const result=await request('/api/v1/integrations/railway/deploy',{method:'POST',body:JSON.stringify({project_id,service_id,environment_id})});report.textContent=`${result.status} · ${result.message} · ID: ${result.deployment_id}`;toast('تم إرسال طلب النشر؛ تحقق من الحالة النهائية.');}
  catch(err){report.textContent=err.message;toast(err.message);}finally{button.disabled=false;}
});

$('#deploymentReadiness').addEventListener('click',async()=>{
  const button=$('#deploymentReadiness');const report=$('#reviewReport');
  button.disabled=true;button.textContent=i18n.rtl?'جارٍ فحص إعدادات النشر...':'Checking deployment settings...';
  report.classList.remove('hidden');report.textContent=i18n.rtl?'جارٍ التحقق من الإعدادات دون نشر المشروع...':'Checking configuration without deploying...';
  try{
    const result=await request('/api/v1/deployment/readiness');report.replaceChildren();
    const heading=document.createElement('h3');
    heading.textContent=i18n.rtl?`حالة الجاهزية: ${result.status} · موانع: ${result.blockers} · تحذيرات: ${result.warnings}`:`Readiness: ${result.status} · Blockers: ${result.blockers} · Warnings: ${result.warnings}`;report.appendChild(heading);
    (result.checks||[]).forEach(item=>{const row=document.createElement('p');row.textContent=`${item.status==='passed'?'✓':item.status==='warning'?'⚠':'✕'} · ${item.message}`;report.appendChild(row);});
    const note=document.createElement('p');note.className='muted';note.textContent=i18n.rtl?'هذا فحص إعدادات فقط؛ لم يتم الاتصال بـ Railway أو نشر أي شيء.':'Preflight only: no Railway connection was made and nothing was deployed.';report.appendChild(note);
  }catch(err){report.textContent=err.message;toast(err.message);}
  finally{button.disabled=false;button.textContent=i18n.rtl?'فحص جاهزية النشر':'Check deployment readiness';}
});

$('#reviewProject').addEventListener('click',async()=>{
  if(!currentProject){toast(i18n.rtl?'اختر مشروعاً أولاً':'Choose a project first');return;}
  const button=$('#reviewProject');const report=$('#reviewReport');button.disabled=true;button.textContent=i18n.rtl?'جارٍ فحص الملفات...':'Reviewing files...';report.classList.remove('hidden');report.textContent=i18n.rtl?'جارٍ فحص ملفات المشروع...':'Reviewing project files...';
  try{
    const result=await request(`/api/v1/projects/${currentProject}/review`,{method:'POST',body:JSON.stringify({preferred_language:i18n.code})});
    report.replaceChildren();const heading=document.createElement('h3');heading.textContent=result.summary;report.appendChild(heading);
    const note=document.createElement('p');note.className='muted';note.textContent=i18n.rtl?`تمت مراجعة ${result.files_reviewed} ملفاً. لم يتم تشغيل الكود أو تعديل الملفات.`:`Reviewed ${result.files_reviewed} files. No code was executed and no files were changed.`;report.appendChild(note);
    (result.findings||[]).forEach(item=>{const card=document.createElement('div');card.className='review-finding';const title=document.createElement('b');title.textContent=`${item.severity.toUpperCase()} · ${item.file}`;const issue=document.createElement('p');issue.textContent=item.issue;const recommendation=document.createElement('p');recommendation.textContent=(i18n.rtl?'التوصية: ':'Recommendation: ')+item.recommendation;const repair=document.createElement('button');repair.type='button';repair.className='secondary';repair.textContent=i18n.rtl?'اقتراح إصلاح ومراجعته':'Prepare and review fix';repair.addEventListener('click',async()=>{repair.disabled=true;try{const preview=await request(`/api/v1/projects/${currentProject}/fix-preview`,{method:'POST',body:JSON.stringify({path:item.file,issue:item.issue,recommendation:item.recommendation})});const approved=window.confirm((i18n.rtl?'اقتراح الإصلاح للملف ':'Proposed fix for ')+preview.path+'\\n\\n'+preview.explanation+'\\n\\n'+(i18n.rtl?'هل توافق على حفظ التعديل؟':'Apply this change?'));if(!approved)return;await request(`/api/v1/projects/${currentProject}/files/${encodeURIComponent(preview.path).replaceAll('%2F','/')}/apply-fix`,{method:'PUT',body:JSON.stringify({expected_sha256:preview.expected_sha256,content:preview.proposed_content})});await loadProjectFiles();toast(i18n.rtl?'تم حفظ الإصلاح':'Fix applied');}catch(err){toast(err.message);}finally{repair.disabled=false;}});card.append(title,issue,recommendation,repair);report.appendChild(card);});
    if(!result.findings.length){const clean=document.createElement('p');clean.textContent=i18n.rtl?'لم يرصد الفحص مشكلات واضحة في الملفات التي تمت مراجعتها.':'No obvious issues were found in the reviewed files.';report.appendChild(clean);}
    toast(i18n.rtl?'اكتمل فحص المشروع':'Project review complete');
  }catch(err){report.textContent=err.message;toast(err.message);}
  finally{button.disabled=false;button.textContent=i18n.rtl?'فحص المشروع بالذكاء الاصطناعي':'Review project with AI';}
});
$('#uploadDeploymentSource').addEventListener('click',()=>{
  if(!currentProject){toast(i18n.rtl?'اختر مشروعاً أولاً':'Choose a project first');return;}
  $('#deploymentSourceInput').click();
});
$('#deploymentSourceInput').addEventListener('change',async e=>{
  const file=e.target.files?.[0];e.target.value='';if(!file)return;
  const button=$('#uploadDeploymentSource'),status=$('#deploymentSourceStatus');
  button.disabled=true;status.textContent=i18n.rtl?'جارٍ رفع وفحص الأرشيف...':'Uploading and validating archive...';
  try{
    const form=new FormData();form.append('file',file);
    const response=await fetch(API+`/api/v1/projects/${currentProject}/deployment-source`,{
      method:'POST',headers:{Authorization:`Bearer ${token}`,'Accept-Language':i18n.code},body:form
    });
    const data=await response.json().catch(()=>({detail:t('requestError')}));
    if(!response.ok)throw new Error(localizeError(data.detail)||t('requestError'));
    status.textContent=i18n.rtl
      ? `تم حفظ وفحص ${data.filename} (${data.file_count} ملفات). لم يتم النشر إلى Railway.`
      : `Validated ${data.filename} (${data.file_count} files). Not deployed to Railway.`;
    toast(i18n.rtl?'تم تجهيز أرشيف المصدر':'Source archive prepared');
  }catch(err){status.textContent=err.message;toast(err.message);}
  finally{button.disabled=false;}
});

$('#buildAndroidPackage').addEventListener('click',async()=>{
  if(!currentProject){toast(i18n.rtl?'اختر مشروعاً أولاً':'Choose a project first');return;}
  const button=$('#buildAndroidPackage');button.disabled=true;
  try{
    const response=await fetch(API+`/api/v1/projects/${currentProject}/android-package`,{headers:{Authorization:`Bearer ${token}`}});
    if(!response.ok){const err=await response.json().catch(()=>({detail:t('requestError')}));throw new Error(localizeError(err.detail)||t('requestError'));}
    const blob=await response.blob();const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`natqai-android-project-${currentProject}.zip`;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast(i18n.rtl?'تم تجهيز مشروع Android Studio. هذا ليس APK جاهزاً بعد.':'Android Studio source package prepared; this is not a compiled APK yet.');
  }catch(err){toast(err.message);}finally{button.disabled=false;}
});


$('#checkAndroidBuilder').addEventListener('click',async()=>{
  if(!currentProject){
    toast(i18n.rtl?'اختر مشروعاً أولاً':'Choose a project first');
    return;
  }

  const button=$('#checkAndroidBuilder');
  const status=$('#androidBuilderStatus');
  button.disabled=true;
  status.textContent=i18n.rtl?'جارٍ فحص خدمة بناء Android...':'Checking Android builder...';

  try{
    const response=await fetch(API+`/api/v1/projects/${currentProject}/android-builder-status`,{
      headers:{Authorization:`Bearer ${token}`}
    });
    const data=await response.json().catch(()=>({detail:t('requestError')}));
    if(!response.ok) throw new Error(localizeError(data.detail)||t('requestError'));

    status.textContent=data.ready
      ? (i18n.rtl?'الخدمة جاهزة لاستقبال طلبات البناء.':'Builder is ready.')
      : (data.message||(i18n.rtl?'خدمة البناء غير جاهزة.':'Builder is not ready.'));
    toast(status.textContent);
  }catch(err){
    status.textContent=err.message;
    toast(err.message);
  }finally{
    button.disabled=false;
  }
});

$('#buildAndroidApk').addEventListener('click',async()=>{
  if(!currentProject){toast(i18n.rtl?'اختر مشروعاً أولاً':'Choose a project first');return;}
  const button=$('#buildAndroidApk');
  if(!window.confirm(i18n.rtl?'هل تؤكد بدء بناء APK الآن؟':'Confirm starting the APK build now?'))return;const original=button.textContent;const status=$('#androidBuilderStatus');button.disabled=true;
  status.textContent=i18n.rtl?'جارٍ فحص خدمة بناء Android...':'Checking Android build service...';
  button.textContent=i18n.rtl?'فحص خدمة البناء...':'Checking build service...';
  try{
    const readiness=await fetch(API+`/api/v1/projects/${currentProject}/android-builder-status`,{
      headers:{Authorization:`Bearer ${token}`}
    });
    const readinessData=await readiness.json().catch(()=>({detail:t('requestError')}));
    if(!readiness.ok)throw new Error(localizeError(readinessData.detail)||t('requestError'));
    if(!readinessData.ready){const message=readinessData.message||(i18n.rtl?'خدمة بناء APK غير جاهزة.':'APK build service is not ready.');status.textContent=message;throw new Error(message);}
    status.textContent=i18n.rtl?'الخدمة جاهزة؛ جارٍ بناء APK...':'Builder is ready; compiling APK...';
    button.textContent=i18n.rtl?'جارٍ بناء APK...':'Building APK...';
    const response=await fetch(API+`/api/v1/projects/${currentProject}/android-apk`,{
      method:'POST',headers:{Authorization:`Bearer ${token}`}
    });
    if(!response.ok){const err=await response.json().catch(()=>({detail:t('requestError')}));throw new Error(localizeError(err.detail)||t('requestError'));}
    const blob=await response.blob();
    if(blob.size<1024||blob.type!=='application/vnd.android.package-archive')throw new Error(i18n.rtl?'لم يُرجع الخادم ملف APK صالحاً.':'Server did not return a valid APK.');
    const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`natqai-debug-${currentProject}.apk`;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),5000);
    status.textContent=i18n.rtl?'اكتمل البناء وتم تنزيل APK بنجاح.':'APK build completed and downloaded successfully.';
    toast(i18n.rtl?'اكتمل البناء وتم تنزيل APK':'APK build completed and downloaded');
  }catch(err){status.textContent=err.message;toast(err.message);}
  finally{button.disabled=false;button.textContent=original;}
});

$('#downloadProject').addEventListener('click',async()=>{
  if(!currentProject){toast(i18n.rtl?'اختر مشروعاً أولاً':'Choose a project first');return;}
  try{
    const response=await fetch(API+`/api/v1/projects/${currentProject}/download`,{headers:{Authorization:`Bearer ${token}`}});
    if(!response.ok){const err=await response.json().catch(()=>({detail:t('requestError')}));throw new Error(localizeError(err.detail)||t('requestError'));}
    const blob=await response.blob();const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`natqai-project-${currentProject}.zip`;document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);
  }catch(err){toast(err.message);}
});
$('#messageForm').addEventListener('submit',e=>{e.preventDefault();sendMessage($('#messageInput').value)});

$('#attachButton').addEventListener('click',()=>$('#attachmentInput').click());

$('#attachmentInput').addEventListener('change',async e=>{
    const files=Array.from(e.target.files||[]);
    e.target.value='';
    if(!files.length)return;

    try{
        if(!currentChat)await createChat();

        for(const file of files){
            const form=new FormData();
            form.append('file',file);

            const response=await fetch(API+`/api/v1/chats/${currentChat}/attachments`,{
                method:'POST',
                headers:{Authorization:`Bearer ${token}`,'Accept-Language':i18n.code},
                body:form
            });

            if(!response.ok){
                const err=await response.json().catch(()=>({detail:t('requestError')}));
                throw new Error(localizeError(err.detail)||t('requestError'));
            }

            const result=await response.json();
            toast(`تم رفع الملف: ${result.original_name}`);
        }

    }catch(err){
        toast(err.message);
    }
});

$('#messageInput').addEventListener('input',e=>{e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,160)+'px'});
$('#messageInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#messageForm').requestSubmit()}});
document.querySelectorAll('.suggestion').forEach(b=>b.addEventListener('click',()=>{const key=b.dataset.promptKey;const prompts={plan:`${t('plan')}: ${t('planDesc')}`,learn:`${t('learn')}: ${t('learnDesc')}`,code:`${t('code')}: ${t('codeDesc')}`,create:`${t('create')}: ${t('createDesc')}`};sendMessage(prompts[key]||t('askExplore'))}));
$('#openSide').addEventListener('click',()=>$('#sidebar').classList.add('open'));
$('#closeSide').addEventListener('click',()=>$('#sidebar').classList.remove('open'));
window.addEventListener('natqai-language-change',()=>{setAuthMode(authMode);if(token)loadChats().catch(()=>{});});
async function boot(){try{await loadProfile();showApp();await loadChats();await loadProjects();await loadUsage();await loadRailwayStatus();if(!currentChat){const chats=await request('/api/v1/chats');if(chats.length)await openChat(chats[0].id);else clearMessages();}}catch(e){logout(false);$('#authError').textContent=e.message;}}
setAuthMode('login');if(token)boot();else showAuth();
