export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Bot Worker is active!", { status: 200 });
    }
    try {
      const update = await request.json();
      await handleUpdate(update, env);
      return new Response("OK", { status: 200 });
    } catch (err) {
      console.error(err);
      return new Response("OK", { status: 200 });
    }
  }
};

async function callTelegram(token, method, payload) {
  const url = `https://api.telegram.org/bot${token}/${method}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return await res.json();
}

async function sendMessage(token, chatId, text, replyMarkup = null, parseMode = "HTML") {
  const payload = { chat_id: chatId, text, parse_mode: parseMode };
  if (replyMarkup) payload.reply_markup = replyMarkup;
  return await callTelegram(token, "sendMessage", payload);
}

async function sendDocument(token, chatId, fileId, caption = "") {
  return await callTelegram(token, "sendDocument", { chat_id: chatId, document: fileId, caption });
}

async function answerCallback(token, id) {
  return await callTelegram(token, "answerCallbackQuery", { callback_query_id: id });
}

async function getSetting(db, key, def = "") {
  const row = await db.prepare("SELECT value FROM settings WHERE key = ?").bind(key).first();
  return row ? row.value : def;
}

async function setSetting(db, key, val) {
  await db.prepare("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value").bind(key, val).run();
}

function userKeyboard() {
  return {
    keyboard: [
      [{ text: "🔗 Taklif havolam" }, { text: "📊 Mening ballarim" }],
      [{ text: "🏆 Reyting (Top-10)" }, { text: "🎁 Sovg'ani olish" }]
    ],
    resize_keyboard: true
  };
}

function adminKeyboard() {
  return {
    inline_keyboard: [
      [{ text: "📊 To'liq statistika", callback_data: "admin_stats" }],
      [{ text: "🎯 Shartni o'zgartirish (Odam soni)", callback_data: "admin_target" }],
      [{ text: "📁 Sovg'a faylini yuklash (PDF/DOC)", callback_data: "admin_gift" }],
      [{ text: "✍️ Kirish matnini o'zgartirish", callback_data: "admin_text" }],
      [{ text: "📢 Foydalanuvchilarga xabar tarqatish", callback_data: "admin_broadcast" }],
      [{ text: "🔄 Natijalarni nollash (Yangi tanlov)", callback_data: "admin_reset" }]
    ]
  };
}

async function handleUpdate(update, env) {
  const token = env.BOT_TOKEN;
  const adminId = parseInt(env.ADMIN_ID, 10);
  const db = env.DB;

  if (update.callback_query) {
    const cq = update.callback_query;
    const fromId = cq.from.id;
    const data = cq.data;
    await answerCallback(token, cq.id);
    if (fromId !== adminId) return;

    if (data === "admin_stats") {
      const uCount = await db.prepare("SELECT COUNT(*) as c FROM users").first();
      const rCount = await db.prepare("SELECT SUM(referrals_count) as c FROM users").first();
      const top = await db.prepare("SELECT user_id, full_name, username, referrals_count FROM users WHERE referrals_count > 0 ORDER BY referrals_count DESC LIMIT 20").all();

      let t = `📊 <b>Statistika:</b>\n👥 Jami a'zolar: <b>${uCount?.c || 0} ta</b>\n🔗 Jami takliflar: <b>${rCount?.c || 0} ta</b>\n\n📋 <b>Faollar:</b>\n`;
      if (top.results && top.results.length > 0) {
        for (const u of top.results) {
          const tag = u.username ? `@${u.username}` : `ID: ${u.user_id}`;
          t += `• ${u.full_name} (${tag}) — <b>${u.referrals_count} ta</b>\n`;
        }
      } else {
        t += `Hali hech kim taklif qilinmagan.\n`;
      }
      await sendMessage(token, fromId, t, adminKeyboard());
    } else if (data === "admin_target") {
      await db.prepare("INSERT INTO admin_states (admin_id, state) VALUES (?, ?) ON CONFLICT(admin_id) DO UPDATE SET state=excluded.state").bind(fromId, "target").run();
      await sendMessage(token, fromId, "Yangi shart sonini yuboring (masalan: 5):");
    } else if (data === "admin_gift") {
      await db.prepare("INSERT INTO admin_states (admin_id, state) VALUES (?, ?) ON CONFLICT(admin_id) DO UPDATE SET state=excluded.state").bind(fromId, "gift").run();
      await sendMessage(token, fromId, "Sovg'a qilinadigan PDF yoki DOC faylni shu yerga tashlang:");
    } else if (data === "admin_text") {
      await db.prepare("INSERT INTO admin_states (admin_id, state) VALUES (?, ?) ON CONFLICT(admin_id) DO UPDATE SET state=excluded.state").bind(fromId, "text").run();
      await sendMessage(token, fromId, "Yangi kirish matnini yuboring:");
    } else if (data === "admin_broadcast") {
      await db.prepare("INSERT INTO admin_states (admin_id, state) VALUES (?, ?) ON CONFLICT(admin_id) DO UPDATE SET state=excluded.state").bind(fromId, "broadcast").run();
      await sendMessage(token, fromId, "Barcha a'zolarga tarqatiladigan xabarni yozing:");
    } else if (data === "admin_reset") {
      await db.prepare("UPDATE users SET referrals_count = 0, gift_sent = 0").run();
      await sendMessage(token, fromId, "🔄 Barcha ballar nollashtirildi!", adminKeyboard());
    }
    return;
  }

  if (update.message) {
    const msg = update.message;
    const userId = msg.from.id;
    const name = [msg.from.first_name, msg.from.last_name].filter(Boolean).join(" ");
    const username = msg.from.username || "";
    const text = msg.text || "";

    if (userId === adminId) {
      const stateRow = await db.prepare("SELECT state FROM admin_states WHERE admin_id = ?").bind(adminId).first();
      if (stateRow && stateRow.state) {
        const state = stateRow.state;
        if (state === "target") {
          if (!/^\d+$/.test(text.trim())) {
            await sendMessage(token, userId, "Faqat musbat son kiriting!");
            return;
          }
          await setSetting(db, "target_count", text.trim());
          await db.prepare("DELETE FROM admin_states WHERE admin_id = ?").bind(adminId).run();
          await sendMessage(token, userId, `✅ Yangi talab: <b>${text.trim()} ta</b> do'st!`, adminKeyboard());
          return;
        }
        if (state === "gift") {
          if (!msg.document) {
            await sendMessage(token, userId, "Iltimos, fayl ko'rinishida yuboring!");
            return;
          }
          await setSetting(db, "gift_file_id", msg.document.file_id);
          await db.prepare("DELETE FROM admin_states WHERE admin_id = ?").bind(adminId).run();
          await sendMessage(token, userId, "✅ Sovg'a fayli saqlandi!", adminKeyboard());
          return;
        }
        if (state === "text") {
          await setSetting(db, "start_text", text);
          await db.prepare("DELETE FROM admin_states WHERE admin_id = ?").bind(adminId).run();
          await sendMessage(token, userId, "✅ Kirish matni saqlandi!", adminKeyboard());
          return;
        }
        if (state === "broadcast") {
          await db.prepare("DELETE FROM admin_states WHERE admin_id = ?").bind(adminId).run();
          await sendMessage(token, userId, "⏳ Xabar tarqatilmoqda...");
          const all = await db.prepare("SELECT user_id FROM users").all();
          let count = 0;
          if (all.results) {
            for (const u of all.results) {
              try { await sendMessage(token, u.user_id, text); count++; } catch (e) {}
            }
          }
          await sendMessage(token, userId, `✅ Xabar <b>${count}</b> ta odamga yetkazildi.`, adminKeyboard());
          return;
        }
      }
    }

    if (text === "/admin" && userId === adminId) {
      await sendMessage(token, userId, "⚙️ <b>Giveaway boshqaruv paneli:</b>", adminKeyboard());
      return;
    }

    if (text.startsWith("/start")) {
      const parts = text.split(" ");
      let inviter = null;
      if (parts.length > 1 && /^\d+$/.test(parts[1])) {
        const parsed = parseInt(parts[1], 10);
        if (parsed !== userId) inviter = parsed;
      }

      const exists = await db.prepare("SELECT user_id FROM users WHERE user_id = ?").bind(userId).first();
      const target = parseInt(await getSetting(db, "target_count", "3"), 10);
      const stText = await getSetting(db, "start_text", "Xush kelibsiz!");

      if (!exists) {
        await db.prepare("INSERT INTO users (user_id, full_name, username, invited_by) VALUES (?, ?, ?, ?)").bind(userId, name, username, inviter).run();
        if (inviter) {
          await db.prepare("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?").bind(inviter).run();
          const iData = await db.prepare("SELECT referrals_count, gift_sent FROM users WHERE user_id = ?").bind(inviter).first();
          if (iData) {
            const cnt = iData.referrals_count;
            try {
              await sendMessage(token, inviter, `🔔 Havolangiz orqali <b>${name}</b> qo'shildi!\nJami takliflaringiz: <b>${cnt}/${target}</b>`);
              if (cnt >= target && !iData.gift_sent) {
                const fId = await getSetting(db, "gift_file_id");
                const cap = await getSetting(db, "gift_caption", "Tabriklaymiz! Sovg'angiz! 🎁");
                if (fId) {
                  await sendDocument(token, inviter, fId, cap);
                  await db.prepare("UPDATE users SET gift_sent = 1 WHERE user_id = ?").bind(inviter).run();
                }
              }
            } catch (e) {}
          }
        }
      }

      const me = await callTelegram(token, "getMe", {});
      const botUser = me.result?.username || "bot";
      const link = `https://t.me/${botUser}?start=${userId}`;
      const msgText = `${stText}\n\n🎯 <b>Shart:</b> ${target} ta do'st taklif qiling.\n🔗 <b>Sizning havolangiz:</b>\n<code>${link}</code>`;
      await sendMessage(token, userId, msgText, userKeyboard());
      return;
    }

    if (text === "🔗 Taklif havolam") {
      const me = await callTelegram(token, "getMe", {});
      const botUser = me.result?.username || "bot";
      await sendMessage(token, userId, `Do'stlaringizni taklif qilish uchun havolangiz:\n\n👉 <code>https://t.me/${botUser}?start=${userId}</code>`, userKeyboard());
      return;
    }

    if (text === "📊 Mening ballarim") {
      const target = parseInt(await getSetting(db, "target_count", "3"), 10);
      const u = await db.prepare("SELECT referrals_count, gift_sent FROM users WHERE user_id = ?").bind(userId).first();
      const cnt = u ? u.referrals_count : 0;
      const st = (u && u.gift_sent) ? "Yuborilgan ✅" : `Qoldi: ${Math.max(0, target - cnt)} ta ⏳`;
      await sendMessage(token, userId, `📊 <b>Sizning ballaringiz:</b>\n\n👥 Taklif qilinganlar: <b>${cnt} ta</b>\n🎯 Kerakli: <b>${target} ta</b>\n🎁 Sovg'a holati: <b>${st}</b>`, userKeyboard());
      return;
    }

    if (text === "🎁 Sovg'ani olish") {
      const target = parseInt(await getSetting(db, "target_count", "3"), 10);
      const u = await db.prepare("SELECT referrals_count FROM users WHERE user_id = ?").bind(userId).first();
      const cnt = u ? u.referrals_count : 0;
      if (cnt >= target) {
        const fId = await getSetting(db, "gift_file_id");
        const cap = await getSetting(db, "gift_caption", "Tabriklaymiz! 🎁");
        if (fId) await sendDocument(token, userId, fId, cap);
        else await sendMessage(token, userId, "Siz shartni bajardingiz! Tez orada sovg'a yuklanadi.");
      } else {
        await sendMessage(token, userId, `Sizga yana <b>${target - cnt}</b> ta taklif kerak!`);
      }
      return;
    }

    if (text === "🏆 Reyting (Top-10)") {
      const top = await db.prepare("SELECT full_name, referrals_count FROM users ORDER BY referrals_count DESC LIMIT 10").all();
      let topT = `🏆 <b>Top-10 taklif qiluvchilar:</b>\n\n`;
      if (top.results && top.results.length > 0) {
        top.results.forEach((u, i) => { topT += `${i + 1}. <b>${u.full_name}</b> — ${u.referrals_count} ta\n`; });
      } else {
        topT += "Hali hech kim yo'q.";
      }
      await sendMessage(token, userId, topT, userKeyboard());
      return;
    }
  }
}