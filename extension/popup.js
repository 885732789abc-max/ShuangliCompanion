document.getElementById('id').textContent='扩展编号：'+chrome.runtime.id;
async function info() {
  const data=await chrome.runtime.sendMessage({type:'info'});
  document.getElementById('status').textContent=data.error || (data.binding?'已绑定原会话'+(data.connected?' · 本机已连接':' · 本机未连接'):'尚未绑定');
}
document.getElementById('bind').addEventListener('click',async()=> {
  const permitted=await chrome.permissions.request({origins:['https://chatgpt.com/*']});
  if (!permitted) return;
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  const result=await chrome.runtime.sendMessage({type:'bind',tabId:tab.id});
  document.getElementById('status').textContent=result.ok?'这页已交给霜璃。':result.error;
});
document.getElementById('revoke').addEventListener('click',async()=> {
  await chrome.runtime.sendMessage({type:'unbind'});await info();
});
info();
