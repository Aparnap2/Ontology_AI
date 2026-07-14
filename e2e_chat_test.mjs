import { chromium } from 'playwright';

const BASE = 'http://localhost:3000';

async function run() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    const errors = [];
    const logs = [];

    page.on('console', msg => logs.push(`[${msg.type()}] ${msg.text()}`));
    page.on('pageerror', err => errors.push(err.message));

    console.log('=== 1. Load /command page ===');
    await page.goto(`${BASE}/command`, { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForSelector('#chat-form', { timeout: 10000 });
    await page.screenshot({ path: '/tmp/e2e-chat-initial.png', fullPage: true });
    console.log('Chat form loaded OK');

    // Wait for HTMX to load the chat history
    await page.waitForSelector('.chat-msg', { timeout: 15000 }).catch(() => console.log('No existing chat messages (fresh DB)'));
    await page.waitForTimeout(2000);

    console.log('=== 2. Send @qa mention message ===');
    // Select @qa mention
    await page.selectOption('select[name="mention"]', '@qa');
    // Type message
    await page.fill('input[name="message"]', 'What is the current mission status?');
    // Click send
    await page.click('button[type="submit"]');
    console.log('Message submitted');

    // Wait for the message to appear
    await page.waitForSelector('.chat-msg', { timeout: 10000 });
    await page.screenshot({ path: '/tmp/e2e-chat-after-send.png', fullPage: true });
    
    // Wait up to 90s for agent response (new chat messages)
    const initialCount = await page.$$eval('.chat-msg', els => els.length);
    console.log(`Initial message count: ${initialCount}`);

    let agentResponded = false;
    for (let i = 0; i < 45; i++) {
        await page.waitForTimeout(2000);
        const currentCount = await page.$$eval('.chat-msg', els => els.length);
        if (currentCount > initialCount) {
            agentResponded = true;
            const texts = await page.$$eval('.chat-msg', els => els.map(e => e.textContent?.substring(0, 150)));
            console.log(`Agent response received! (${currentCount} messages)`);
            texts.forEach((t, i) => console.log(`  msg ${i + 1}: ${t}`));
            break;
        }
        process.stdout.write('.');
    }

    await page.screenshot({ path: '/tmp/e2e-chat-agent-response.png', fullPage: true });

    console.log('\n=== 3. Results ===');
    console.log(`Agent responded: ${agentResponded}`);
    console.log(`Page errors: ${errors.length > 0 ? errors.join(', ') : 'none'}`);
    console.log(`Console logs:`);
    logs.filter(l => l.includes('error') || l.includes('Error') || l.includes('SSE')).forEach(l => console.log(`  ${l}`));

    await browser.close();
    process.exit(agentResponded ? 0 : 1);
}

run().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
