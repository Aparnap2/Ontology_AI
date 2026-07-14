import { chromium } from 'playwright';

const BASE = 'http://localhost:3000';

async function run() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    page.on('console', msg => console.log(`[BROWSER ${msg.type()}] ${msg.text().substring(0, 200)}`));

    // Step 1: Load page, send message
    console.log('=== 1. Load /command ===');
    await page.goto(`${BASE}/command`, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForSelector('#chat-form', { timeout: 10000 });
    await page.waitForTimeout(3000);
    console.log('SSE status:', await page.$eval('#chat-conn-label', el => el.textContent).catch(() => 'n/a'));

    // Send message
    console.log('=== 2. Send @sarthi message ===');
    await page.selectOption('select[name="mention"]', '@sarthi');
    await page.fill('input[name="message"]', 'What is the current mission status?');
    await page.click('button[type="submit"]');
    console.log('Submitted');

    // Wait for answer via SSE
    for (let i = 0; i < 30; i++) {
        await page.waitForTimeout(3000);
        const msgs = await page.$$eval('.chat-msg', els => els.map(e => e.textContent));
        const hasAgent = msgs.some(m => m.includes('mission') || m.includes('status') || m.includes('OntologyAI'));
        if (hasAgent) {
            console.log('=== AGENT ANSWER FOUND VIA SSE ===');
            msgs.forEach((m, j) => console.log(`  msg[${j}]: ${m.substring(0, 150)}`));
            await page.screenshot({ path: '/tmp/e2e-chat-sse.png', fullPage: true });
            await browser.close();
            process.exit(0);
        }
        process.stdout.write('.');
    }

    console.log('\n=== 3. No SSE answer. Check DB via HTMX reload... ===');

    // Trigger HTMX reload of chat
    await page.evaluate(() => {
        htmx.trigger('#chat-container', 'load');
    });
    await page.waitForTimeout(2000);

    const msgsAfterReload = await page.$$eval('.chat-msg', els => els.map(e => e.textContent));
    console.log('Messages after reload:');
    msgsAfterReload.forEach((m, j) => console.log(`  msg[${j}]: ${m.substring(0, 200)}`));

    const hasPersisted = msgsAfterReload.some(m => m.includes('mission') || m.includes('status'));
    
    await page.screenshot({ path: '/tmp/e2e-chat-db.png', fullPage: true });
    await browser.close();
    
    if (hasPersisted) {
        console.log('\n✓ ANSWER PERSISTED IN DB (confirmed via HTMX reload)');
        process.exit(0);
    } else {
        console.log('\n✗ No answer found even after reload');
        process.exit(1);
    }
}

run().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
