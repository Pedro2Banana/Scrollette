from dataclasses import dataclass


@dataclass
class ReadingState:
    page_index: int = 0
    zoom: float = 1.0
    two_page: bool = False

    @property
    def page_step(self):
        return 2 if self.two_page else 1

    def reset_for_new_document(self):
        self.page_index = 0
        self.zoom = 1.0

    def visible_indices(self, page_count):
        indices = [self.page_index]
        if self.two_page and self.page_index + 1 < page_count:
            indices.append(self.page_index + 1)
        return indices

    def previous_page(self):
        self.page_index = max(0, self.page_index - self.page_step)

    def next_page(self, page_count):
        self.page_index = min(self.page_index + self.page_step, page_count - 1)
