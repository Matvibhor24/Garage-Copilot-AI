// Customer page strings in English and Hindi (C12). No i18n library: one dictionary, one lookup.
// English is the default; the choice is remembered on this device.
import { useState } from 'react'

export const LANGS = { en: 'English', hi: 'हिंदी' }

export const STRINGS = {
  en: {
    job: 'Job {id}',
    live: 'Live',
    linkBroken: 'Link not working',
    linkExpired: 'This link has expired or is not valid. Ask the garage to send it again.',
    yourVehicle: 'Your vehicle',
    finalBillAmount: 'Final bill {amount}',
    waitingForOk: 'Waiting for your OK on extra work',
    since: 'Since {time}',
    progress: 'Progress',
    now: 'now',
    'stage.intake': 'Checked in',
    'stage.service': 'In service',
    'stage.waiting_approval': 'Waiting for your approval',
    'stage.washing': 'Washing',
    'stage.ready': 'Ready for pickup',
    'stage.done': 'Ready for pickup',
    quote: 'Quote {id}',
    plusLabour: '{parts} + labour',
    approved: 'Approved',
    approvedAuto: 'Approved automatically',
    withinLimit: "Within the garage's {amount} limit",
    declined: 'Declined',
    approvedThanks: 'Thanks! The mechanic has been told to go ahead.',
    declinedOk: 'No problem. Nothing extra will be done.',
    approvalNeeded: 'Your approval needed',
    extraWork: 'Extra work found',
    photoAlt: 'Photo from the mechanic',
    labour: 'Labour',
    service: 'Service charge',
    total: 'Total',
    approveAmount: 'Approve {amount}',
    keepIt: 'Keep it',
    yesDecline: 'Yes, decline',
    decline: 'Decline',
    limitNote: '{owner}work above {amount} always waits for your OK.',
    finalBill: 'Final bill',
    billSoFar: 'Bill so far',
    updatesItself: 'This page updates by itself. No app needed.',
    messages: 'Messages from the garage',
    readMessage: 'Read the message',
    hideMessage: 'Hide the message',
    'kind.status_link': 'Status link',
    'kind.quote': 'Quote',
    'kind.final_bill': 'Final bill',
    'kind.other': 'Message',
    error: 'Something went wrong. Please try again.',
    language: 'Language',
    callGarage: 'Call the garage',
  },
  hi: {
    job: 'जॉब {id}',
    live: 'लाइव',
    linkBroken: 'लिंक काम नहीं कर रहा',
    linkExpired: 'यह लिंक पुराना हो गया है या सही नहीं है। गैराज से इसे फिर से भेजने को कहें।',
    yourVehicle: 'आपकी गाड़ी',
    finalBillAmount: 'अंतिम बिल {amount}',
    waitingForOk: 'अतिरिक्त काम के लिए आपकी मंज़ूरी का इंतज़ार',
    since: '{time} से',
    progress: 'प्रगति',
    now: 'अभी',
    'stage.intake': 'गाड़ी जमा हुई',
    'stage.service': 'सर्विस चल रही है',
    'stage.waiting_approval': 'आपकी मंज़ूरी का इंतज़ार',
    'stage.washing': 'धुलाई',
    'stage.ready': 'ले जाने के लिए तैयार',
    'stage.done': 'ले जाने के लिए तैयार',
    quote: 'कोटेशन {id}',
    plusLabour: '{parts} + मज़दूरी',
    approved: 'मंज़ूर',
    approvedAuto: 'अपने-आप मंज़ूर',
    withinLimit: 'गैराज की {amount} की सीमा के अंदर',
    declined: 'मना किया',
    approvedThanks: 'धन्यवाद! मैकेनिक को काम शुरू करने के लिए बता दिया गया है।',
    declinedOk: 'कोई बात नहीं। कोई अतिरिक्त काम नहीं होगा।',
    approvalNeeded: 'आपकी मंज़ूरी चाहिए',
    extraWork: 'अतिरिक्त काम मिला',
    photoAlt: 'मैकेनिक की भेजी फोटो',
    labour: 'मज़दूरी',
    service: 'सर्विस चार्ज',
    total: 'कुल',
    approveAmount: '{amount} मंज़ूर करें',
    keepIt: 'रहने दें',
    yesDecline: 'हाँ, मना करें',
    decline: 'मना करें',
    limitNote: '{owner}{amount} से ऊपर का काम हमेशा आपकी मंज़ूरी के बाद ही होता है।',
    finalBill: 'अंतिम बिल',
    billSoFar: 'अब तक का बिल',
    updatesItself: 'यह पेज अपने-आप अपडेट होता है। कोई ऐप नहीं चाहिए।',
    messages: 'गैराज के संदेश',
    readMessage: 'संदेश पढ़ें',
    hideMessage: 'संदेश छिपाएँ',
    'kind.status_link': 'स्टेटस लिंक',
    'kind.quote': 'कोटेशन',
    'kind.final_bill': 'अंतिम बिल',
    'kind.other': 'संदेश',
    error: 'कुछ गड़बड़ हुई। कृपया फिर से कोशिश करें।',
    language: 'भाषा',
    callGarage: 'गैराज को कॉल करें',
  },
}

export function t(lang, key, vars = {}) {
  const text = STRINGS[lang]?.[key] ?? STRINGS.en[key] ?? key
  return text.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? ''))
}

const KEY = 'gc.customer.lang'

export function readCustomerLang() {
  try {
    const v = localStorage.getItem(KEY)
    return v in LANGS ? v : 'en'
  } catch {
    return 'en'
  }
}

export function useCustomerLang() {
  const [lang, setLang] = useState(readCustomerLang)
  function choose(next) {
    try { localStorage.setItem(KEY, next) } catch { /* private mode */ }
    setLang(next)
  }
  return [lang, choose]
}

// A quote's or message's text in the chosen language (falls back to whatever text there is).
export function textIn(lang, item) {
  return (lang === 'hi' ? item.text_hi : item.text_en) || item.text_en || item.text || ''
}
