'use strict'

const { lightpanda } = require('@lightpanda/browser');
const puppeteer = require('puppeteer-core');
const TurndownService = require('turndown');
const { gfm } = require('turndown-plugin-gfm');
const cheerio = require('cheerio');
const { encoding_for_model, get_encoding } = require('@dqbd/tiktoken');

const lpdopts = {
  host: '127.0.0.1',
  port: 9222,
};

const puppeteeropts = {
  browserWSEndpoint: `ws://${lpdopts.host}:${lpdopts.port}`,
};

function countTokens(text) {
  const enc = (encoding_for_model && encoding_for_model('gpt-4o-mini'))
    || get_encoding('cl100k_base');

  try {
    return enc.encode(text).length;
  } finally {
    enc.free();
  }
}

async function getPageContent(url) {
  let proc, browser, page, rawHtml;
  try {
    proc = await lightpanda.serve(lpdopts);
    browser = await puppeteer.connect(puppeteeropts);

    const context = await browser.createBrowserContext();
    page = await context.newPage();

    // Простой вызов без параметров, как в рабочем примере
    await page.goto(url);

    rawHtml = await page.content();

    await page.close();
    await context.close();
    await browser.disconnect();

    return { rawHtml, proc };
  } catch (err) {
    console.error('Error in getPageContent:', err.message || err);

    if (page) await page.close().catch(() => {});
    if (browser) await browser.disconnect().catch(() => {});
    if (proc) {
      proc.stdout.destroy();
      proc.stderr.destroy();
      proc.kill();
    }
    throw err;
  }
}

(async () => {
  const args = process.argv.slice(2);
  const url = args.find(arg => !arg.startsWith('--'));

  if (!url) {
    console.error('Error: URL not provided');
    process.exit(1);
  }

  let rawHtml = '<body><p>Unreachable</p></body>';
  let proc;

  try {
    const result = await getPageContent(url);
    console.log('Processed');
    rawHtml = result.rawHtml;
    proc = result.proc;
  } catch (err) {
    console.log('Failed');
    console.error(err?.stack || err?.toString() || 'Unknown error');
  }

  // --- НАЧИНАЕМ ОБРАБОТКУ HTML ---
  console.log('!**********!');

  const $ = cheerio.load(rawHtml);
  const $body = $('body');

  $body.find('script,style,noscript,img').remove();
  $body.find('a').replaceWith(function () { return $(this).html() || ''; });

  (function rmComments(node) {
    node.contents().each(function () {
      if (this.type === 'comment') $(this).remove();
      else if (this.type === 'tag') rmComments($(this));
    });
  })($body);

  $body.find('th, td').each(function () {
    $(this).text($(this).text().replace(/\s+/g, ' ').trim());
  });
  $body.find('table').each(function () {
    const first = $(this).find('tr').first();
    if (first.find('th').length === 0) {
      first.find('td').each(function () {
        $(this).replaceWith($('<th>').text($(this).text()));
      });
    }
  });

  const cleanedHtml = $body.html();

  let markdown;
  try {
    const td = new TurndownService();
    td.use(gfm);
    markdown = td.turndown(cleanedHtml);
  } catch (_) {
    try {
      const td2 = new TurndownService();
      td2.keep(['table','thead','tbody','tr','th','td']);
      markdown = td2.turndown(cleanedHtml);
    } catch (_) {
      markdown = cleanedHtml;
    }
  }

  const tokenLimit = 100_000;
  try {
    const tokens = countTokens(markdown);
    console.log(`Tokens: ${tokens}`);
    console.log();
    console.log();
    if (tokens > tokenLimit) {
      console.log('too much tokens');
    } else {
      console.log(markdown);
    }
  } catch (e) {
    console.error('Token counter error:', e?.message || e);
    console.log(`Chars (fallback): ${markdown.length}`);
    console.log(markdown.length > 600_000 ? 'too much tokens' : markdown);
  }

  // Останавливаем Lightpanda
  if (proc) {
    proc.stdout.destroy();
    proc.stderr.destroy();
    proc.kill();
  }
})();