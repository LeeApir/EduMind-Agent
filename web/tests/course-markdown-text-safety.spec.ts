import { mount, flushPromises } from '@vue/test-utils';
import { afterEach, expect, it, vi } from 'vitest';
import CourseReading from '../src/components/CourseReading.vue';

const markdown = '~~~c\nint scores[6];\nprintf("%d\\n", scores[3]);\n<script>window.bad = true</script>\n<img src=x onerror="bad()">\n[x](https://example.com)\n~~~';
vi.mock('../src/api/freeCourses', () => ({
  readScene: vi.fn(async () => ({
    course_id: 'course', course_version: 1, scene_id: 'scene', scene_version_id: 'version',
    blocks: [{ kind: 'text', anchor_id: 'a', markdown }], actions: [],
  })),
}));
afterEach(() => vi.clearAllMocks());
it('displays code characters exactly as text without active tags, links or images', async () => {
  const wrapper = mount(CourseReading, { props: { courseId: 'course', version: 1, sceneId: 'scene' } });
  await flushPromises();
  expect(wrapper.get('.scene-prose').element.textContent?.trim()).toBe(markdown);
  expect(wrapper.text()).toContain('scores[6]');
  expect(wrapper.text()).toContain('printf("%d\\n", scores[3]);');
  expect(wrapper.findAll('script,img,a,iframe,svg,object')).toHaveLength(0);
  wrapper.unmount();
});
