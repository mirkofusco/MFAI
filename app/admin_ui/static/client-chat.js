let sessionId = localStorage.getItem("chat_session_id");

async function send(msg){
  const res = await fetch(location.pathname + "/chat", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({session_id: sessionId, message: msg})
  });
  const data = await res.json();
  if(!sessionId && data.session_id){
    sessionId = data.session_id;
    localStorage.setItem("chat_session_id", sessionId);
  }
  return data.reply || "";
}

const log = document.getElementById("log");
document.getElementById("f").addEventListener("submit", async (e)=>{
  e.preventDefault();
  const msg = e.target.msg.value.trim();
  if(!msg) return;
  log.textContent += "🧑 " + msg + "\n";
  e.target.msg.value = "";
  const reply = await send(msg);
  log.textContent += "🤖 " + reply + "\n\n";
  log.scrollTop = log.scrollHeight;
});
