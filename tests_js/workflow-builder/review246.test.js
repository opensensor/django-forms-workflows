import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkflowBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder.js';
import { createWorkflowBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder-store.js';

function createInstance() {
  const instance = Object.create(WorkflowBuilder.prototype);
  instance.store = createWorkflowBuilderStore();
  instance.fields = [];
  instance.groups = [];
  instance.forms = [];
  instance.validationState = { nodeIssues: {} };
  instance.render = vi.fn();
  instance.selectNode = vi.fn();
  return instance;
}

beforeEach(() => {
  document.body.innerHTML = '<div id="propertiesContent"></div>';
});

describe('workflow builder review fixes', () => {
  it('selects a node by keyboard and restores focus to its new header', () => {
    const instance = createInstance();
    const node = { id: 'stage-1', type: 'stage', x: 0, y: 0, data: { name: 'Review' } };
    const host = document.createElement('div');
    document.body.appendChild(host);
    host.appendChild(instance.createNodeElement(node));
    instance.selectNode = vi.fn(() => {
      host.replaceChildren(instance.createNodeElement(node));
    });

    const header = host.querySelector('.node-header');
    expect(header.getAttribute('role')).toBe('button');
    expect(header.getAttribute('aria-label')).toBe('Select Review to edit properties');
    header.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    expect(instance.selectNode).toHaveBeenCalledWith(node.id);
    expect(document.activeElement).toBe(host.querySelector('.node-header'));
  });

  it('restores header focus after both drag renders', () => {
    const instance = createInstance();
    const node = { id: 'stage-1', type: 'stage', x: 0, y: 0, data: { name: 'Review' } };
    const host = document.createElement('div');
    document.body.appendChild(host);
    instance.transformWrapper = host;
    instance.render = vi.fn(() => host.replaceChildren(instance.createNodeElement(node)));
    instance.selectNode = vi.fn(() => instance.render());
    instance.bringNodeToFront = vi.fn();
    instance.clientToCanvas = (x, y) => [x, y];
    instance.render();

    host.querySelector('.node-header').dispatchEvent(new MouseEvent('mousedown', {
      button: 0, bubbles: true, clientX: 10, clientY: 10,
    }));
    expect(document.activeElement).toBe(host.querySelector('.node-header'));
    document.dispatchEvent(new MouseEvent('mouseup'));
    expect(document.activeElement).toBe(host.querySelector('.node-header'));
  });

  it('labels the delete action with the escaped node name', () => {
    const instance = createInstance();
    const element = instance.createNodeElement({
      id: 'stage-1', type: 'stage', x: 0, y: 0,
      data: { name: 'Review "urgent"' },
    });
    const button = element.querySelector('.node-actions button');

    expect(button.getAttribute('aria-label')).toBe('Delete node: Review "urgent"');
    expect(button.getAttribute('type')).toBe('button');
    expect(button.querySelector('i').getAttribute('aria-hidden')).toBe('true');
  });

  it('keeps untrusted node types inside the icon class attribute', () => {
    const instance = createInstance();
    const element = instance.createNodeElement({
      id: 'stage-1', type: 'stage" onmouseover="alert(1)', x: 0, y: 0,
      data: { name: 'Review' },
    });

    expect(element.querySelector('.node-icon').hasAttribute('onmouseover')).toBe(false);
  });

  it('keeps a scrolled canvas cursor fixed while zooming', () => {
    document.body.innerHTML = '<div id="workflowCanvas"><svg id="connectionsSvg"></svg></div>';
    const instance = createInstance();
    instance.zoom = 1;
    instance.minZoom = 0.25;
    instance.maxZoom = 2;
    instance.panX = 0;
    instance.panY = 0;
    instance.updateWorkspaceBounds = vi.fn();
    instance.applyTransform = vi.fn();
    instance.updateZoomIndicator = vi.fn();
    instance.setupCanvas();
    instance.canvas.scrollLeft = 40;
    instance.canvas.scrollTop = 20;
    instance.canvas.getBoundingClientRect = () => ({ left: 100, top: 50 });

    instance.canvas.dispatchEvent(new WheelEvent('wheel', {
      bubbles: true,
      cancelable: true,
      clientX: 200,
      clientY: 150,
      deltaY: -1,
    }));

    expect(instance.zoom).toBeCloseTo(1.1);
    expect(instance.panX).toBeCloseTo(-14);
    expect(instance.panY).toBeCloseTo(-12);
  });

  it('keeps the visible canvas center fixed when zooming with the toolbar', () => {
    const instance = createInstance();
    instance.canvas = document.createElement('div');
    instance.canvas.scrollLeft = 40;
    instance.canvas.scrollTop = 20;
    instance.canvas.getBoundingClientRect = () => ({ width: 200, height: 100 });
    instance.zoom = 1;
    instance.minZoom = 0.25;
    instance.maxZoom = 2;
    instance.panX = 0;
    instance.panY = 0;
    instance.applyTransform = vi.fn();
    instance.updateZoomIndicator = vi.fn();

    instance.setZoom(1.5);

    expect(instance.panX).toBe(-70);
    expect(instance.panY).toBe(-35);
  });

  it('allows only same-origin form links and keeps URL text inside href', () => {
    const instance = createInstance();
    const renderLink = url => {
      const wrapper = document.createElement('div');
      wrapper.innerHTML = instance.buildFormProperties({ data: { form_builder_url: url } });
      return wrapper.querySelector('a');
    };

    expect(renderLink('javascript:alert(1)').getAttribute('href')).toBe('#');
    expect(renderLink('https://example.com/edit').getAttribute('href')).toBe('#');
    expect(renderLink(`${window.location.origin}//example.com/edit`).getAttribute('href')).toBe('#');
    expect(renderLink('/admin/forms/1/edit/').getAttribute('href')).toBe('/admin/forms/1/edit/');
    expect(renderLink('#details').getAttribute('href')).toBe('#details');
    const injected = renderLink('/admin/forms/?q=" onmouseover="alert(1)');
    expect(injected.hasAttribute('onmouseover')).toBe(false);
  });

  it('sanitizes form links shown inside graph nodes', () => {
    const instance = createInstance();
    const wrapper = document.createElement('div');
    wrapper.innerHTML = instance.getNodeDescription({
      type: 'form',
      data: { field_count: 1, form_builder_url: '/admin/forms/?q=" onmouseover="alert(1)' },
    });
    const link = wrapper.querySelector('a');
    expect(link.hasAttribute('onmouseover')).toBe(false);
    expect(link.getAttribute('href')).toContain('/admin/forms/');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');

    wrapper.innerHTML = instance.getNodeDescription({
      type: 'form',
      data: { field_count: 1, form_builder_url: 'javascript:alert(1)' },
    });
    expect(wrapper.querySelector('a').getAttribute('href')).toBe('#');
  });

  it('moves the selected role when a group appears in two roles', () => {
    const instance = createInstance();
    const node = {
      id: 'stage_1',
      type: 'stage',
      data: {
        name: 'Review',
        approval_groups: [
          { id: 1, name: 'Reviewers', role: 'approval', position: 0 },
          { id: 1, name: 'Reviewers', role: 'validation', position: 1 },
        ],
      },
    };
    instance.nodes = [node];
    instance.groups = [{ id: 1, name: 'Reviewers' }];

    instance.showNodeProperties(node);
    document.querySelector('[data-stage-group-role="validation"][data-stage-group-direction="-1"]').click();

    expect(node.data.approval_groups.map(group => group.role)).toEqual(['validation', 'approval']);
  });
});
