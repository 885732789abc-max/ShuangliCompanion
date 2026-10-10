(() => {
  if (globalThis.__shuangliBridge) return;
  globalThis.__shuangliBridge = true;
  const VERSION = 'dom-visible-v1';
  let authorized = '', active = null, timer = null, observer = null;
  let latestSnapshot = '', lastState = '', historyAt = 0;
  const completed = new Set();
  const seenIds = new Set();
  const visible = el => !!el && !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
  const normalized = text => String(text).replace(/\r/g,'').trim();
  const pageURL = () => location.origin + location.pathname.replace(/\/$/,'');
  function emit(event) {
    if (!authorized || pageURL()!==authorized) return;
    chrome.runtime.sendMessage({type:'event',event:{...event,url:authorized,adapter:VERSION}}).catch(()=>{});
  }
  function editor() {
    const matches = [...document.querySelectorAll('#prompt-textarea,textarea[data-testid="prompt-textarea"],div[contenteditable="true"][data-placeholder]')].filter(visible);
    return matches.length===1 ? matches[0] : null;
  }
  function stopButton() {
    return [...document.querySelectorAll('[data-testid="stop-button"],button[aria-label="Stop generating"],button[aria-label="停止生成"]')].find(visible);
  }
  function sendButton() {
    return [...document.querySelectorAll('[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="发送提示"]')].find(visible);
  }
  function readText(root) {
    // Only public rendered message text. Reasoning/status details are excluded.
    function markdown(node) {
      if (node.nodeType===Node.TEXT_NODE) return node.textContent;
      if (node.nodeType!==Node.ELEMENT_NODE) return '';
      if (!visible(node) || node.matches('script,style,button,svg,[hidden],[aria-hidden="true"],details,[data-testid*="reasoning"],[data-testid*="thought"],[class*="reasoning"]')) return '';
      const body=[...node.childNodes].map(markdown).join('');
      switch(node.tagName) {
        case 'PRE': return '\n```\n'+node.textContent+'\n```\n';
        case 'CODE': return node.parentElement?.tagName==='PRE'?body:'`'+body+'`';
        case 'P': case 'DIV': return body+'\n\n';
        case 'BR': return '\n';
        case 'STRONG': case 'B': return '**'+body+'**';
        case 'EM': case 'I': return '*'+body+'*';
        case 'LI': return '- '+body+'\n';
        case 'BLOCKQUOTE': return '\n> '+body.trim()+'\n';
        case 'H1': case 'H2': case 'H3': return '\n'+'#'.repeat(Number(node.tagName[1]))+' '+body+'\n';
        case 'A': {
          const href=node.getAttribute('href')||'';
          return /^https?:\/\//.test(href)?'['+body+']('+href+')':body;
        }
        default:return body;
      }
    }
    return markdown(root).trim().replace(/\n{3,}/g,'\n\n').slice(0,100000);
  }
  function messages() {
    return [...document.querySelectorAll('[data-message-author-role="user"],[data-message-author-role="assistant"]')].filter(visible).slice(-30).map((el,index)=> {
      const role=el.getAttribute('data-message-author-role');
      const content=role==='assistant'?el.querySelector('.markdown, .prose'):el;
      const turn=el.closest('[data-testid^="conversation-turn"],article') || el;
      const id=el.getAttribute('data-message-id') || turn.id || 'visible-'+index;
      const done=role==='assistant' && [...turn.querySelectorAll('[data-testid="copy-turn-action-button"],button[aria-label="Copy"],button[aria-label="复制"]')].some(visible);
      return {role,text:content?readText(content):'',id,done};
    });
  }
  function tick() {
    if (!authorized) return;
    if (pageURL()!==authorized) { revoke(); return; }
    const input=editor();
    const busy=!!stopButton();
    const compatible=!!input && !!document.querySelector('[data-message-author-role]');
    const state=JSON.stringify([compatible,busy]);
    if (state!==lastState) {
      lastState=state; emit({type:'status',compatible,state:busy?'generating':'idle'});
    }
    const list=messages();
    const snapshot=JSON.stringify(list.map(({done,...m})=>m));
    if (snapshot!==latestSnapshot && Date.now()-historyAt>800) {
      latestSnapshot=snapshot;historyAt=Date.now();
      emit({type:'snapshot',messages:list.map(({done,...m})=>m)});
    }
    if (!active) return;
    const newUsers=list.filter(m=>m.role==='user'&&!active.baseline.has(m.id));
    const sent=newUsers.find(m=>normalized(m.text)===normalized(active.text));
    if (sent && !active.observed) {
      active.observed=true;active.userId=sent.id;
      emit({type:'sent',id:active.id});
    }
    if (busy) active.sawGenerating=true;
    if (active.observed) {
      const userIndex=list.findIndex(m=>m.id===active.userId);
      const response=list.slice(userIndex+1).find(m=>m.role==='assistant'&&!active.baseline.has(m.id));
      if (response?.text) {
        const done=response.done && !busy;
        if (response.text!==active.lastText || done) {
          active.lastText=response.text;
          emit({type:'reply',id:response.id,text:response.text,done});
        }
        if (done) {completed.add(active.id);active=null;}
      }
    }
    if (active && Date.now()-active.started>120000 && !active.observed) {
      emit({type:'error',id:active.id,message:'网页没有确认消息，请回原会话检查；霜璃不会重发。',uncertain:true});
      active=null;
    }
  }
  function revoke() {
    authorized='';active=null;
    clearInterval(timer);timer=null;
    observer?.disconnect();observer=null;
  }
  async function send(msg) {
    if (pageURL()!==authorized || msg.url!==authorized || typeof msg.text!=='string' || msg.text.length>20000 || !/^[a-f0-9]{32}$/.test(msg.id)) return;
    if (seenIds.has(msg.id) || completed.has(msg.id) || active) {
      emit({type:'error',id:msg.id,message:'这条消息已经处理，或上一条仍在等待。',uncertain:false});return;
    }
    const input=editor();
    if (!input || stopButton() || normalized(input.value??input.innerText)) {
      emit({type:'error',id:msg.id,message:'网页正在生成，或输入框已有草稿；请先处理原页面。',uncertain:false});return;
    }
    seenIds.add(msg.id);
    const baseline=new Set(messages().map(m=>m.id));
    input.focus();
    if (input instanceof HTMLTextAreaElement) {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(input,msg.text);
      input.dispatchEvent(new Event('input',{bubbles:true}));
    } else if (input.isContentEditable) {
      const selection=getSelection();const range=document.createRange();
      range.selectNodeContents(input);selection.removeAllRanges();selection.addRange(range);
      // Browser editing command updates ProseMirror's input state; no private React API.
      if (!document.execCommand('insertText',false,msg.text)) {
        emit({type:'error',id:msg.id,message:'原页面编辑器不兼容，请在网页发送。',uncertain:false});return;
      }
    } else {emit({type:'error',id:msg.id,message:'输入控件不兼容。',uncertain:false});return;}
    await new Promise(resolve=>setTimeout(resolve,200));
    const button=sendButton();
    if (pageURL()!==authorized || !button || button.disabled) {
      emit({type:'error',id:msg.id,message:'网页发送按钮不可用，草稿留在原页面。',uncertain:false});return;
    }
    if (normalized(input.value??input.innerText)!==normalized(msg.text)) {
      emit({type:'error',id:msg.id,message:'网页草稿已变化，霜璃停止发送。',uncertain:false});return;
    }
    active={id:msg.id,text:msg.text,baseline,started:Date.now(),observed:false,lastText:''};
    button.click();tick();
  }
  chrome.runtime.onMessage.addListener((msg,_sender,respond)=> {
    if (msg.type==='authorize' && msg.url===pageURL()) {
      revoke();authorized=msg.url;lastState='';latestSnapshot='';
      timer=setInterval(()=> {tick();emit({type:'heartbeat'});},2000);
      let scheduled=false;
      observer=new MutationObserver(()=> {
        if (!scheduled) {scheduled=true;setTimeout(()=> {scheduled=false;tick();},200);}
      });
      observer.observe(document.querySelector('main')||document.body,{childList:true,subtree:true,characterData:true});
      tick(); respond({ok:true});
    } else if (msg.type==='revoke') {revoke();respond({ok:true});}
    else if (msg.type==='send') {send(msg).catch(()=>emit({type:'error',id:msg.id,message:'网页操作中断，请检查原会话。',uncertain:true}));respond({ok:true});}
  });
})();
