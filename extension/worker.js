const HOST = 'com.shuangli.conversation_bridge';
let port = null;
let binding = null;
let target = '';
let connectionError = '';

function canonical(raw) {
  try {
    const u = new URL(raw);
    if (u.origin !== 'https://chatgpt.com' || !/^\/(?:g\/[A-Za-z0-9_-]+\/)?c\/[A-Za-z0-9_-]+\/?$/.test(u.pathname)) return '';
    return u.origin + u.pathname.replace(/\/$/, '');
  } catch { return ''; }
}

async function loadBinding() {
  if (!binding) binding = (await chrome.storage.session.get('binding')).binding || null;
  return binding;
}

function connect() {
  if (port) return;
  connectionError = '';
  port = chrome.runtime.connectNative(HOST);
  port.onDisconnect.addListener(() => {
    connectionError = chrome.runtime.lastError?.message || '本机连接已断开';
    port = null;
    chrome.action.setBadgeText({text:'!'});
  });
  port.onMessage.addListener(async msg => {
    const b = await loadBinding();
    if (msg.type === 'target') {
      target = canonical(msg.url);
      if (b && target === b.url) {
        port?.postMessage({type:'bound',url:b.url});
        try { await chrome.tabs.sendMessage(b.tabId,{type:'authorize',url:b.url}); } catch {}
      }
      return;
    }
    if (msg.type === 'send') {
      if (!b || canonical(msg.url) !== b.url || target !== b.url) {
        port?.postMessage({type:'error',url:canonical(msg.url),message:'授权页与桌宠所选会话不一致。',uncertain:false});
        return;
      }
      try {
        const tab = await chrome.tabs.get(b.tabId);
        if (canonical(tab.url) !== b.url) throw new Error('授权页已切换会话。');
        await chrome.tabs.sendMessage(b.tabId,{type:'send',id:msg.id,text:msg.text,url:b.url});
      } catch (e) {
        port?.postMessage({type:'error',url:b.url,id:msg.id,message:String(e.message).slice(0,200),uncertain:false});
      }
    }
  });
}

chrome.runtime.onMessage.addListener((msg, sender, respond) => {
  (async () => {
    if (sender.id !== chrome.runtime.id) return respond({ok:false});
    if (msg.type === 'bind' && !sender.tab) {
      const tab = await chrome.tabs.get(msg.tabId);
      const url = canonical(tab.url);
      if (!url) return respond({ok:false,error:'请打开已有的 ChatGPT 对话，再绑定这一页。'});
      const old = await loadBinding();
      if (old) try { await chrome.tabs.sendMessage(old.tabId,{type:'revoke'}); } catch {}
      binding = {tabId:tab.id,url}; target=url;
      await chrome.storage.session.set({binding});
      await chrome.scripting.executeScript({target:{tabId:tab.id},files:['content.js']});
      connect();
      port?.postMessage({type:'bound',url});
      await chrome.tabs.sendMessage(tab.id,{type:'authorize',url});
      chrome.action.setBadgeText({text:'连'});
      return respond({ok:true,url});
    }
    if (msg.type === 'unbind' && !sender.tab) {
      const b = await loadBinding();
      if (b) {
        port?.postMessage({type:'unbind',url:b.url});
        try { await chrome.tabs.sendMessage(b.tabId,{type:'revoke'}); } catch {}
      }
      binding=null; target='';
      await chrome.storage.session.remove('binding');
      port?.disconnect();port=null;
      chrome.action.setBadgeText({text:''});
      return respond({ok:true});
    }
    if (msg.type === 'info' && !sender.tab) {
      return respond({ok:true,binding:await loadBinding(),error:connectionError,connected:!!port});
    }
    if (msg.type === 'event' && sender.tab) {
      const b = await loadBinding();
      if (!b || sender.tab.id!==b.tabId || canonical(sender.url)!==b.url || canonical(msg.event?.url)!==b.url) return respond({ok:false});
      const event = msg.event;
      if (!['heartbeat','snapshot','status','reply','sent','error'].includes(event.type)) return respond({ok:false});
      if (JSON.stringify(event).length > 800000) return respond({ok:false});
      // Reconnect only on explicit popup binding. No hidden retries or sends.
      port?.postMessage(event);
      respond({ok:!!port});
      return;
    }
    respond({ok:false});
  })().catch(e => respond({ok:false,error:String(e.message).slice(0,200)}));
  return true;
});

chrome.tabs.onRemoved.addListener(async id => {
  const b = await loadBinding();
  if (b?.tabId===id) {
    port?.postMessage({type:'unbind',url:b.url});
    binding=null;await chrome.storage.session.remove('binding');
    port?.disconnect();port=null;
  }
});
