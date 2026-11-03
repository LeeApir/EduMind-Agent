"""Assemble a bounded offline lesson; never execute C or contact a provider."""
import hashlib
import html
import json
import re
from pathlib import Path

from scripts.isolated_diagnostics.generate_p15_real_candidate_player import build
from scripts.isolated_diagnostics.p15_minimal_contract import verify_artifact

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCES = {
    'model_candidate': 'docs/acceptance/phase-1.5-combined-candidate-r01/results/candidate.json',
    'original_player': 'docs/acceptance/phase-1.5-real-candidate-player-t098/course.html',
    'chinese_revision': 'docs/acceptance/phase-1.5-teaching-revision-t100/assistant-revision.json',
    'assessment': 'docs/acceptance/phase-1.5-real-course-independent-t099/ASSESSMENT.md',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assemble():
    original_html = build()  # Existing T098 code/state/action validation, unchanged.
    assert original_html == (ROOT / SOURCES['original_player']).read_text()
    data = json.loads(re.search(r'<script id="sample-data" type="application/json">(.*?)</script>', original_html, re.S)[1])
    original = json.loads((ROOT / SOURCES['model_candidate']).read_text())
    revision = json.loads((ROOT / SOURCES['chinese_revision']).read_text())
    verify_artifact(revision)
    assert revision['identity']['parent_digest'] == original['artifact_digest']
    assert revision['source']['actions'] == original['source']['actions']
    old_blocks = original['source']['blocks']
    blocks = revision['source']['blocks']
    assert [b['text'] for b in blocks if b['kind'] == 'code'] == [data['code']]
    assert [b['answer_key'] for b in blocks if b['kind'] == 'question'] == [b['answer_key'] for b in old_blocks if b['kind'] == 'question']
    data['version'] = 'unified-head-zh-v1'
    paragraphs = [p.copy() for p in revision['raw_output']['paragraphs']]
    paragraphs[-1]['text'] = paragraphs[-1]['text'].replace('本轨迹只展示两次成功路径，没有单独高亮判空行，也没有演示失败分支或释放内存。', '原轨迹只展示两次成功路径；本页补入两次成功判空展示，未演示分配失败或释放内存。')
    data['paragraphs'] = paragraphs
    data['questions'] = [b for b in blocks if b['kind'] == 'question']
    data['frames'] = []
    notes = {
        'initial': '从 caller_head 出发，初始只有 i0(9)。函数尚未调用，局部 head 和 p 不在作用域。',
        'allocate': '分配新结点，p 指向它。data 和 next 尚未初始化，不能读取其值。调用者的头尚未改变。',
        'data': '判空成功后，写入新结点的 data。此时 next 仍未知，还没有接上旧链表。',
        'link': '令 p->next = head，把新结点接到旧头之前；caller_head 此刻仍指向旧头。',
        'return': 'return p 把新结点地址交回调用者。这里显示返回前的函数状态，调用者尚未接收。',
        'caller': '调用者接收返回值，更新 caller_head。局部 head 和 p 已离开作用域，动态结点仍然存活。',
    }
    titles = {'initial':'初始链表','allocate':'分配结点','data':'写入数据','link':'连接旧头','return':'返回新头','caller':'调用者接回'}
    for index, state in enumerate(data['states']):
        data['frames'].append({'state_index':index, 'line':state['code_line'], 'title':titles[state['phase']], 'note':notes[state['phase']], 'origin':'program_projection', 'source_actions':[i for i,a in enumerate(data['actions']) if a['step']==index]})
        if state['phase'] == 'allocate':
            data['frames'].append({'state_index':index,'line':5,'title':'检查分配结果','note':'本例假定 p 非空，p == NULL 为假，继续执行第 6 行。这里复用分配后的状态，不改变任何指针。失败分支未回放。','origin':'assistant_success_check','source_actions':[]})
    data['provenance'] = {'sources':{k:{'path':v,'sha256':sha(ROOT/v)} for k,v in SOURCES.items()}, 'model_digest':original['artifact_digest'],'revision_digest':revision['artifact_digest'],'example_digest':revision['source']['example_digest'],'engine':revision['source']['engine_version'],'template':revision['source']['template_version'],'text_mapping':'paragraphs[*].key → T100 raw_output.paragraphs; questions[*].anchor/observation_key → T100 source.blocks → T095 source.blocks (order/answer unchanged). final_observation contains T103 coverage wording update.','frame_mapping':'frames[*].state_index → T098 states; source_actions → original 31 actions; two assistant_success_check frames reuse states 1/6 and highlight code line 5. All frame notes and titles are assistant authored.','production_scoring':False,'new_model_requests':0}
    encoded = json.dumps(data,ensure_ascii=False,indent=2)
    (OUT/'lesson.json').write_text(encoded+'\n')
    payload = encoded.replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    page = (OUT/'template.html').read_text().replace('__PAYLOAD__',payload)
    page = page.replace('__PARAGRAPHS__',''.join('<p>'+html.escape(p['text'])+'</p>' for p in paragraphs))
    (OUT/'course.html').write_text(page)
    manifest = {p.name:sha(p) for p in [OUT/'lesson.json',OUT/'course.html',OUT/'template.html',Path(__file__)]}
    (OUT/'manifest.json').write_text(json.dumps({'version':data['version'],'sources':data['provenance']['sources'],'outputs':manifest},ensure_ascii=False,indent=2)+'\n')
    print('Built unified-head-zh-v1: 13 frames, 4 questions; original code/answers/11 states/31 actions unchanged.')


if __name__ == '__main__':
    assemble()
