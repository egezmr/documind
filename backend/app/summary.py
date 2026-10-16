"""Select source passages and validate traceable synthesized summaries."""
import difflib
import re
import unicodedata

HEADINGS = ['Hakkımda', 'Deneyim', 'Eğitim', 'Sertifikalar', 'Aktiviteler', 'Topluluklar', 'Beceriler', 'İlgi alanları']


def fold(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c)).replace('ı', 'i')


def heading(line):
    key = re.sub(r'[^a-z]', '', fold(line))
    names = {re.sub(r'[^a-z]', '', fold(h)): h for h in HEADINGS}
    match = difflib.get_close_matches(key, names, n=1, cutoff=.85) if len(key) >= 6 else []
    return names[match[0]] if match else None


def passages(sources):
    result = []
    section, document = 'Belge', None
    for source in sources:
        if document != source['name']:
            section, document = 'Belge', source['name']
        buffer = []
        has_headings = any(heading(line.strip()) for line in source['text'].splitlines())
        prose_started = False
        def flush():
            separator = '\n' if section in {'Eğitim', 'Beceriler'} else ' '
            text = separator.join(' '.join(line.split()) for line in buffer)
            if text:
                # Keep sentences together; only split unusually long passages.
                sentences = re.split(r'(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ])', text)
                for sentence in sentences:
                    if not sentence.strip():
                        continue
                    result.append({'id': len(result) + 1, 'section': section, 'text': sentence, 'name': source['name']})
            buffer.clear()
        for line in source['text'].splitlines():
            found = heading(line.strip())
            if found:
                flush()
                section = found
                prose_started = False
            elif re.search(r'@|https?://|\+\d[\d ()-]{7,}', line) or re.fullmatch(r'[\w-]+/', line.strip()):
                flush()
            elif section == 'Belge' and has_headings:
                continue
            elif section in {'Deneyim', 'Hakkımda'} and not prose_started and len(line.strip()) < 70 and not re.search(r'[.!?]$', line.strip()):
                continue
            else:
                prose_started = True
                buffer.append(line.strip())
        flush()
    return result


def select_passages(passages, chosen):
    by_id = {p['id']: p for p in passages}
    selected = []
    for ident in chosen:
        if type(ident) is int and ident in by_id and ident not in selected:
            selected.append(ident)
    # Ensure key sections are represented even when the model omits them.
    required = []
    for section in ['Eğitim', 'Beceriler', 'Sertifikalar', 'Topluluklar']:
        entries = [p for p in passages if p['section'] == section]
        if entries:
            required.append(entries[0]['id'])
        if entries and not any(by_id[i]['section'] == section for i in selected):
            selected.append(entries[0]['id'])
    if not selected:
        selected = [p['id'] for p in passages[:6]]
    selected = sorted(dict.fromkeys(required + selected[:6]))
    return [by_id[i] for i in selected]


def render(passages, chosen):
    return 'Belgeden seçilen ana bilgiler:\n\n' + '\n\n'.join('• ' + p['text'] for p in select_passages(passages, chosen))


def validate_synthesis(data, evidence, minimum=3):
    """Check traceability and known risky claims; not full semantic entailment."""
    if not isinstance(data, dict) or not isinstance(data.get('sentences'), list):
        raise ValueError('Özet cümleleri eksik.')
    by_id = {p['id']: p['text'] for p in evidence}
    sentences = []
    for item in data['sentences']:
        if not isinstance(item, dict):
            raise ValueError('Geçersiz özet cümlesi.')
        text, ids = item.get('text'), item.get('evidence_ids')
        if not isinstance(text, str) or not text.strip() or len(text) > 600:
            raise ValueError('Özet cümlesi boş veya çok uzun.')
        if not isinstance(ids, list) or not ids or any(type(i) is not int or i not in by_id for i in ids):
            raise ValueError('Cümle için geçerli belge kanıtı belirtilmeli.')
        support = fold(' '.join(by_id[i] for i in ids))
        claim = fold(text)
        if re.search(r'\b(?:ben|geliştiricisiyim|çalıştım|geliştirdim|yaptım|öğrendim|buldum|odaklandım|deneyimim|kazandım|hâkimim|mezunuyum)\b', text.casefold()):
            raise ValueError('Özet üçüncü şahısla yazılmalı; belgedeki birinci şahıs dili kopyalanmamalı.')
        for term in ['yuksek lisans', 'doktora', 'lisans', 'on lisans', 'master', 'phd', 'msc', 'uzman']:
            if re.search(r'\b' + term + r'\w*', claim) and not re.search(r'\b' + term + r'\w*', support):
                raise ValueError(f'Kaynakta bulunmayan eğitim/uzmanlık ifadesi: {term}')
        if not set(re.findall(r'\d+', text)).issubset(set(re.findall(r'\d+', support))):
            raise ValueError('Kaynakta bulunmayan tarih veya sayı.')
        sentences.append(text.strip())
    if not minimum <= len(sentences) <= 5:
        raise ValueError('Özet 3-5 cümle içermeli.')
    paragraph = ' '.join(sentences)
    if len(re.findall(r'[.!?](?:\s|$)', paragraph)) > 5 or len(paragraph.split()) > 110:
        raise ValueError('Özet fazla uzun. Toplam 3-5 kısa cümle ve en fazla 110 kelime kullan.')
    return paragraph


def combine_valid_sentences(items, evidence):
    """Retain only validated claims across retries, then select a short overview."""
    pool = []
    seen = set()
    for item in items:
        try:
            text = validate_synthesis({'sentences': [item]}, evidence, minimum=1)
        except (ValueError, TypeError):
            continue
        for sentence in re.split(r'(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ])', text):
            if fold(sentence) not in seen:
                seen.add(fold(sentence))
                pool.append({'text': sentence, 'evidence_ids': item['evidence_ids']})
    if len(pool) < 3:
        raise ValueError('Yeterli güvenilir özet cümlesi yok.')
    overviews = [p for p in pool if re.match(r'^(Bu belge|Belgede|Belge,)', p['text'])]
    first = max(overviews or pool[:1], key=lambda p: len(p['text']))
    selected = [first]
    pool.remove(first)
    covered = set(first['evidence_ids'])
    while pool and len(selected) < 3:
        best = max(pool, key=lambda p: (len(set(p['evidence_ids']) - covered), len(set(fold(p['text']).split()) - set(fold(' '.join(s['text'] for s in selected)).split()))))
        pool.remove(best)
        if sum(len(s['text'].split()) for s in selected) + len(best['text'].split()) <= 110:
            selected.append(best)
            covered.update(best['evidence_ids'])
    return validate_synthesis({'sentences': selected}, evidence)
